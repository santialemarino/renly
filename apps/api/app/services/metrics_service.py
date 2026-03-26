# Business logic for investment and portfolio metrics.

from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ExchangeRateUnavailableError, NotFoundError
from app.models.investment import Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
from app.repositories.group_repository import group_repository
from app.repositories.investment_repository import investment_repository
from app.repositories.metrics_repository import metrics_repository
from app.schemas.metrics import (
    AllocationItem,
    AllocationResponse,
    EvolutionPoint,
    GroupAllocationItem,
    GroupAllocationResponse,
    InvestmentMetricsResponse,
    InvestmentsSummaryResponse,
    InvestmentSummaryItem,
    PeriodReturnItem,
    PortfolioEvolutionResponse,
    PortfolioMetricsResponse,
    SkippedInvestment,
)
from app.services import metrics_helpers as mh

ZERO = Decimal("0")
ONE = Decimal("1")


# Splits investments into convertible and skipped based on currency support.
# When no currency is requested, all investments are convertible (no conversion needed).
def _split_by_convertibility(
    investments: list[Investment],
    currency: str | None,
) -> tuple[list[Investment], list[SkippedInvestment]]:
    if not currency:
        return investments, []
    convertible: list[Investment] = []
    skipped: list[SkippedInvestment] = []
    for inv in investments:
        if mh.can_convert(inv.base_currency, currency):
            convertible.append(inv)
        else:
            skipped.append(
                SkippedInvestment(
                    investment_id=inv.id,
                    name=inv.name,
                    base_currency=inv.base_currency,
                )
            )
    return convertible, skipped


# Resolves the filtered list of active investments based on optional filters.
# When no filters are provided, returns all active investments for the user.
async def _resolve_filtered_investments(
    session: AsyncSession,
    user_id: int,
    investment_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
) -> list[Investment]:
    investments = await metrics_repository.list_active_investments(session, user_id)
    if not investments:
        return []

    # Filter by specific investment IDs.
    if investment_ids:
        allowed = set(investment_ids)
        investments = [i for i in investments if i.id in allowed]

    # Filter by group membership (union of all groups).
    if group_ids:
        member_ids: set[int] = set()
        for gid in group_ids:
            ids = await group_repository.get_investment_ids_by_group(session, gid)
            member_ids.update(ids)
        investments = [i for i in investments if i.id in member_ids]

    # Filter by category.
    if category:
        investments = [i for i in investments if i.category == category]

    # Filter by name (case-insensitive).
    if search:
        term = search.lower()
        investments = [i for i in investments if term in i.name.lower()]

    return investments


# Computes metrics for a single investment (TWR, IRR, period returns, etc.).
# When currency is provided, converts absolute values via USD pivot.
async def get_investment_metrics(
    session: AsyncSession,
    investment_id: int,
    user_id: int,
    currency: str | None = None,
) -> InvestmentMetricsResponse:
    inv = await investment_repository.get_by_id(session, investment_id, user_id)
    if inv is None:
        raise NotFoundError(f"Investment {investment_id} not found.")

    snapshots = await metrics_repository.list_snapshots_by_investments(session, [investment_id])
    transactions = await metrics_repository.list_transactions_by_investments(session, [investment_id])

    rate_map = await _get_required_rate_map(session, currency, [inv])
    return _build_investment_metrics(inv, snapshots, transactions, currency, rate_map)


# Computes portfolio-level metrics (total value, invested, gain, month change).
# When currency is provided, converts all monetary values via USD pivot.
async def get_portfolio_metrics(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PortfolioMetricsResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, group_ids, category, search)
    investments, skipped = _split_by_convertibility(all_investments, currency)
    if not investments:
        return PortfolioMetricsResponse(
            total_value=ZERO,
            total_invested=ZERO,
            absolute_gain=ZERO,
            currency=currency,
            skipped_investments=skipped,
        )

    rate_map = await _get_required_rate_map(session, currency, investments)
    inv_ids = [i.id for i in investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    latest_map = {inv_id: snaps[-1] for inv_id, snaps in snap_by_inv.items()}
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)

    # Build a lookup from investment_id to base_currency.
    inv_currency = {i.id: i.base_currency for i in investments}

    # Total current value.
    total_value = ZERO
    for inv_id, snap in latest_map.items():
        v = snap.value
        if currency and rate_map:
            v = mh.convert_value(v, inv_currency.get(inv_id, ""), currency, rate_map)
        total_value += v

    # Total invested capital.
    total_invested = ZERO
    for inv_id in inv_ids:
        cap = mh.invested_capital(tx_by_inv.get(inv_id, []))
        if currency and rate_map:
            cap = mh.convert_value(cap, inv_currency.get(inv_id, ""), currency, rate_map)
        total_invested += cap

    absolute_gain = total_value - total_invested

    # Simple return is only meaningful when invested capital is positive.
    total_return_pct = None
    if total_invested > ZERO:
        total_return_pct = total_value / total_invested - ONE

    # Month-over-month change.
    curr_for_change = ZERO
    prev_total = ZERO
    has_prev = False
    for inv_id in inv_ids:
        snaps = snap_by_inv.get(inv_id, [])
        if len(snaps) >= 2:
            curr_v = snaps[-1].value
            prev_v = snaps[-2].value
            if currency and rate_map:
                base = inv_currency.get(inv_id, "")
                curr_v = mh.convert_value(curr_v, base, currency, rate_map)
                prev_v = mh.convert_value(prev_v, base, currency, rate_map)
            curr_for_change += curr_v
            prev_total += prev_v
            has_prev = True

    month_change = (curr_for_change - prev_total) if has_prev else None
    month_change_pct = None
    if has_prev and prev_total != ZERO:
        month_change_pct = (curr_for_change - prev_total) / prev_total

    # Portfolio TWR: compute monthly portfolio-level returns, then chain.
    # For each unique date, sum all investment values (forward-fill + convert).
    # Then compute period return between consecutive portfolio totals.
    all_dates: set[date_type] = set()
    inv_date_value: dict[int, dict[date_type, Decimal]] = {}
    for inv_id, snaps in snap_by_inv.items():
        dv: dict[date_type, Decimal] = {}
        for s in snaps:
            v = s.value
            if currency and rate_map:
                v = mh.convert_value(v, inv_currency.get(inv_id, ""), currency, rate_map)
            dv[s.date] = v
            all_dates.add(s.date)
        inv_date_value[inv_id] = dv

    sorted_dates = sorted(all_dates)

    # Build portfolio totals per date (forward-fill).
    last_known: dict[int, Decimal] = {}
    portfolio_totals: list[tuple[date_type, Decimal]] = []
    for d in sorted_dates:
        total = ZERO
        for inv_id in inv_ids:
            dv = inv_date_value.get(inv_id, {})
            if d in dv:
                last_known[inv_id] = dv[d]
            total += last_known.get(inv_id, ZERO)
        portfolio_totals.append((d, total))

    # Compute net cash flows per period and chain returns.
    portfolio_returns: list[Decimal] = []
    for i in range(1, len(portfolio_totals)):
        prev_date, prev_val = portfolio_totals[i - 1]
        curr_date, curr_val = portfolio_totals[i]
        # Sum net cash flows across all investments in this period.
        period_ncf = ZERO
        for inv_id in inv_ids:
            ncf = mh.net_cash_flow(tx_by_inv.get(inv_id, []), prev_date, curr_date)
            if currency and rate_map:
                ncf = mh.convert_value(ncf, inv_currency.get(inv_id, ""), currency, rate_map)
            period_ncf += ncf
        r = mh.period_return(prev_val, curr_val, period_ncf)
        if r is not None:
            if start_date and curr_date < start_date:
                continue
            if end_date and curr_date > end_date:
                continue
            portfolio_returns.append(r)
    portfolio_twr = mh.twr(portfolio_returns)

    # Portfolio IRR: combined cashflow series across all investments.
    # Convert each cashflow to the display currency so mixed-currency portfolios are meaningful.
    all_cashflows: list[tuple[date_type, float]] = []
    for inv_id in inv_ids:
        snaps = snap_by_inv.get(inv_id, [])
        txs = tx_by_inv.get(inv_id, [])
        cfs = mh.build_irr_cashflows(snaps, txs)
        base = inv_currency.get(inv_id, "")
        if currency and rate_map:
            cfs = [(d, float(mh.convert_value(Decimal(str(a)), base, currency, rate_map))) for d, a in cfs]
        if start_date or end_date:
            cfs = [(d, a) for d, a in cfs if (not start_date or d >= start_date) and (not end_date or d <= end_date)]
        all_cashflows.extend(cfs)
    portfolio_irr = mh.xirr(all_cashflows) if len(all_cashflows) >= 2 else None

    return PortfolioMetricsResponse(
        total_value=total_value,
        total_invested=total_invested,
        absolute_gain=absolute_gain,
        total_return_pct=total_return_pct,
        twr=portfolio_twr,
        irr=portfolio_irr,
        month_change=month_change,
        month_change_pct=month_change_pct,
        currency=currency,
        skipped_investments=skipped,
    )


# Computes monthly portfolio value series for the evolution chart.
# Forward-fills missing months so each investment contributes its last known value.
async def get_portfolio_evolution(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PortfolioEvolutionResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, group_ids, category, search)
    investments, skipped = _split_by_convertibility(all_investments, currency)
    if not investments:
        return PortfolioEvolutionResponse(points=[], currency=currency, skipped_investments=skipped)

    rate_map = await _get_required_rate_map(session, currency, investments)
    inv_ids = [i.id for i in investments]
    inv_currency = {i.id: i.base_currency for i in investments}

    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)

    # Build {investment_id: {date: value}} lookup.
    inv_date_value: dict[int, dict[date_type, Decimal]] = {}
    all_dates: set[date_type] = set()
    for inv_id, snaps in snap_by_inv.items():
        date_map: dict[date_type, Decimal] = {}
        for s in snaps:
            date_map[s.date] = s.value
            all_dates.add(s.date)
        inv_date_value[inv_id] = date_map

    if not all_dates:
        return PortfolioEvolutionResponse(points=[], currency=currency)

    # Generate all months from earliest to latest snapshot date.
    min_date = min(all_dates)
    max_date = max(all_dates)
    all_months: list[date_type] = []
    cursor = date_type(min_date.year, min_date.month, 1)
    end = date_type(max_date.year, max_date.month, 1)
    while cursor <= end:
        all_months.append(cursor)
        if cursor.month == 12:
            cursor = date_type(cursor.year + 1, 1, 1)
        else:
            cursor = date_type(cursor.year, cursor.month + 1, 1)

    # Remap snapshots to their month (first of month) for lookup.
    inv_month_value: dict[int, dict[date_type, Decimal]] = {}
    for inv_id, date_map in inv_date_value.items():
        month_map: dict[date_type, Decimal] = {}
        for d, v in date_map.items():
            month_key = date_type(d.year, d.month, 1)
            month_map[month_key] = v
        inv_month_value[inv_id] = month_map

    # For each month, sum values across investments (forward-fill missing months).
    points: list[EvolutionPoint] = []
    last_known: dict[int, Decimal] = {}
    for month in all_months:
        total = ZERO
        for inv_id in inv_ids:
            month_map = inv_month_value.get(inv_id, {})
            if month in month_map:
                last_known[inv_id] = month_map[month]
            val = last_known.get(inv_id, ZERO)
            if currency and rate_map:
                val = mh.convert_value(val, inv_currency.get(inv_id, ""), currency, rate_map)
            total += val
        points.append(EvolutionPoint(date=month, total_value=total))

    # Filter points by date range if provided.
    if start_date:
        points = [p for p in points if p.date >= start_date]
    if end_date:
        points = [p for p in points if p.date <= end_date]

    return PortfolioEvolutionResponse(points=points, currency=currency, skipped_investments=skipped)


# Computes allocation by investment category.
# When currency is provided, converts values via USD pivot.
async def get_allocation(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
) -> AllocationResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, group_ids, category, search)
    investments, skipped = _split_by_convertibility(all_investments, currency)
    if not investments:
        return AllocationResponse(items=[], total_value=ZERO, skipped_investments=skipped)

    rate_map = await _get_required_rate_map(session, currency, investments)
    inv_ids = [i.id for i in investments]
    latest_map = await metrics_repository.get_latest_snapshots(session, inv_ids)

    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for inv in investments:
        snapshot = latest_map.get(inv.id)
        if snapshot:
            v = snapshot.value
            if currency and rate_map:
                v = mh.convert_value(v, inv.base_currency, currency, rate_map)
            cat_values[inv.category] += v

    total_value = sum(cat_values.values(), ZERO)

    items = []
    for category, value in sorted(cat_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_value * 100) if total_value != ZERO else ZERO
        items.append(AllocationItem(category=category, value=value, percentage=pct))

    return AllocationResponse(items=items, total_value=total_value, skipped_investments=skipped)


# Computes allocation by investment group.
# Investments not in any group are bucketed under "Ungrouped".
async def get_allocation_by_group(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
) -> GroupAllocationResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, group_ids, category, search)
    investments, skipped = _split_by_convertibility(all_investments, currency)
    if not investments:
        return GroupAllocationResponse(items=[], total_value=ZERO, skipped_investments=skipped)

    rate_map = await _get_required_rate_map(session, currency, investments)
    inv_ids = [i.id for i in investments]
    inv_currency = {i.id: i.base_currency for i in investments}
    latest_map = await metrics_repository.get_latest_snapshots(session, inv_ids)

    # Build {investment_id: converted_value} for investments with snapshots.
    inv_values: dict[int, Decimal] = {}
    for inv_id, snapshot in latest_map.items():
        v = snapshot.value
        if currency and rate_map:
            v = mh.convert_value(v, inv_currency.get(inv_id, ""), currency, rate_map)
        inv_values[inv_id] = v

    # Load groups and their memberships.
    groups = await group_repository.list_by_user(session, user_id)
    grouped_inv_ids: set[int] = set()
    group_values: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for group in groups:
        member_ids = await group_repository.get_investment_ids_by_group(session, group.id)
        for mid in member_ids:
            if mid in inv_values:
                group_values[group.name] += inv_values[mid]
                grouped_inv_ids.add(mid)

    # Ungrouped bucket.
    ungrouped = ZERO
    for inv_id, val in inv_values.items():
        if inv_id not in grouped_inv_ids:
            ungrouped += val
    if ungrouped > ZERO:
        group_values["Ungrouped"] = ungrouped

    total_value = sum(group_values.values(), ZERO)

    items = []
    for name, value in sorted(group_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_value * 100) if total_value != ZERO else ZERO
        items.append(GroupAllocationItem(group_name=name, value=value, percentage=pct))

    return GroupAllocationResponse(items=items, total_value=total_value, skipped_investments=skipped)


# Computes lightweight per-investment metrics for the dashboard compact table.
# Returns current value, invested capital, absolute gain, and month-over-month change.
async def get_investments_summary(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> InvestmentsSummaryResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, group_ids, category, search)
    investments, skipped = _split_by_convertibility(all_investments, currency)
    if not investments:
        return InvestmentsSummaryResponse(items=[], skipped_investments=skipped)

    rate_map = await _get_required_rate_map(session, currency, investments)
    inv_ids = [i.id for i in investments]

    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)

    items: list[InvestmentSummaryItem] = []
    for inv in investments:
        snaps = snap_by_inv.get(inv.id, [])
        txs = tx_by_inv.get(inv.id, [])
        base = inv.base_currency

        # Check if the investment has any snapshots within the selected date range.
        has_snapshots_in_period = True
        if start_date or end_date:
            has_snapshots_in_period = any(
                (start_date is None or s.date >= start_date) and (end_date is None or s.date <= end_date) for s in snaps
            )

        current_value = snaps[-1].value if snaps else None
        cap = mh.invested_capital(txs)
        absolute_gain = (current_value - cap) if current_value is not None else None

        # Month-over-month change.
        month_change_pct = None
        if len(snaps) >= 2:
            curr_v = snaps[-1].value
            prev_v = snaps[-2].value
            if prev_v != ZERO:
                month_change_pct = (curr_v - prev_v) / prev_v

        # Convert absolute values.
        if currency and rate_map:
            if current_value is not None:
                current_value = mh.convert_value(current_value, base, currency, rate_map)
            cap = mh.convert_value(cap, base, currency, rate_map)
            absolute_gain = (current_value - cap) if current_value is not None else None

        items.append(
            InvestmentSummaryItem(
                investment_id=inv.id,
                name=inv.name,
                category=inv.category,
                current_value=current_value,
                invested_capital=cap,
                absolute_gain=absolute_gain,
                month_change_pct=month_change_pct,
                has_snapshots_in_period=has_snapshots_in_period,
                currency=currency or base,
            )
        )

    # Sort by current value descending (None values last).
    items.sort(key=lambda x: x.current_value or ZERO, reverse=True)

    return InvestmentsSummaryResponse(items=items, skipped_investments=skipped)


# Returns a rate map for pivot conversion.
# Raises ExchangeRateUnavailableError if conversion is needed but no rates are available.
# Returns None when currency is None (no conversion requested).
async def _get_required_rate_map(
    session: AsyncSession,
    currency: str | None,
    investments: list[Investment],
) -> dict[str, Decimal] | None:
    if not currency:
        return None
    target_base = mh.base_currency(currency)
    needs_conversion = any(inv.base_currency != target_base for inv in investments)
    if not needs_conversion:
        return None
    rate_map = await mh.get_rate_map(session, currency)
    if rate_map is None:
        raise ExchangeRateUnavailableError(currency)
    return rate_map


# Builds InvestmentMetricsResponse from raw data.
# When currency and rate_map_map are provided, converts absolute values via USD pivot.
def _build_investment_metrics(
    investment: Investment,
    snapshots: list[InvestmentSnapshot],
    transactions: list[Transaction],
    currency: str | None = None,
    rate_map: dict[str, Decimal] | None = None,
) -> InvestmentMetricsResponse:
    cap = mh.invested_capital(transactions)
    current_value = snapshots[-1].value if snapshots else None
    absolute_gain = (current_value - cap) if current_value is not None else None

    simple_return = None
    if current_value is not None and cap != ZERO:
        simple_return = current_value / cap - ONE

    # Period returns.
    pr_data = mh.compute_period_returns(snapshots, transactions)

    # TWR: chain valid period returns.
    valid_returns = [r for _, _, r in pr_data if r is not None]
    twr_val = mh.twr(valid_returns)

    # IRR: annualised money-weighted return.
    irr_cashflows = mh.build_irr_cashflows(snapshots, transactions)
    irr_val = mh.xirr(irr_cashflows)

    # Convert absolute values if currency requested.
    base = investment.base_currency
    if currency and rate_map:
        if current_value is not None:
            current_value = mh.convert_value(current_value, base, currency, rate_map)
        cap = mh.convert_value(cap, base, currency, rate_map)
        absolute_gain = (current_value - cap) if current_value is not None else None

    period_returns = [
        PeriodReturnItem(
            date=d,
            value=mh.convert_value(v, base, currency, rate_map) if currency and rate_map else v,
            return_pct=r,
        )
        for d, v, r in pr_data
    ]

    return InvestmentMetricsResponse(
        investment_id=investment.id,
        name=investment.name,
        category=investment.category,
        base_currency=base,
        current_value=current_value,
        invested_capital=cap,
        absolute_gain=absolute_gain,
        simple_return=simple_return,
        twr=twr_val,
        irr=irr_val,
        period_returns=period_returns,
        currency=currency or base,
    )
