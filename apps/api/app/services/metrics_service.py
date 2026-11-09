# Business logic for investment and portfolio metrics.

import calendar as _calendar
from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ExchangeRateUnavailableError, NotFoundError
from app.models.investment import Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.repositories.collection_repository import collection_repository
from app.repositories.investment_repository import investment_repository
from app.repositories.metrics_repository import metrics_repository
from app.schemas.metrics import (
    AllocationItem,
    AllocationResponse,
    CollectionAllocationItem,
    CollectionAllocationResponse,
    EvolutionPoint,
    InvestmentMetricsResponse,
    InvestmentsSummaryResponse,
    InvestmentSummaryItem,
    PeriodReturnItem,
    PortfolioEvolutionResponse,
    PortfolioMetricsResponse,
    SkippedInvestment,
)
from app.services import exchange_rate_service, settings_service
from app.utils import metrics as mh
from app.utils.pagination import MAX_LIST_ROWS

ZERO = Decimal("0")
ONE = Decimal("1")


# Splits investments into convertible and skipped. An investment is skipped when its base
# currency is statically unsupported OR when the rates needed to reach the display currency
# are missing from the stored data (fail-loud: a value must never pass through unconverted).
# When no currency is requested, all investments are convertible (no conversion needed).
def _split_by_convertibility(
    investments: list[Investment],
    currency: str | None,
    lookup: mh.RateLookup | None,
) -> tuple[list[Investment], list[SkippedInvestment]]:
    if not currency:
        return investments, []
    rate_map = lookup.get_rate_map_at(date_type.today()) if lookup else None
    convertible: list[Investment] = []
    skipped: list[SkippedInvestment] = []
    for inv in investments:
        base = inv.base_currency
        data_present = rate_map is not None and base in rate_map and currency in rate_map
        if base == currency or (mh.can_convert(base, currency) and data_present):
            convertible.append(inv)
        else:
            skipped.append(
                SkippedInvestment(
                    investment_id=inv.id,
                    name=inv.name,
                    base_currency=base,
                )
            )
    return convertible, skipped


# Resolves the filtered list of active investments based on optional filters.
# When no filters are provided, returns all active investments for the user.
async def _resolve_filtered_investments(
    session: AsyncSession,
    user_id: int,
    investment_ids: list[int] | None = None,
    collection_ids: list[int] | None = None,
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

    # Filter by collection membership (union of all collections) — batch query.
    if collection_ids:
        ids_by_collection = await collection_repository.get_investment_ids_by_collections(session, collection_ids)
        member_ids = {mid for ids in ids_by_collection.values() for mid in ids}
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

    lookup = await _get_required_lookup(session, user_id, currency, [inv])
    # Single-investment endpoint has no skip list — a missing pair is a hard 503, never a
    # silently unconverted number.
    today = None
    if currency and lookup is not None:
        rate_map = lookup.get_rate_map_at(date_type.today())
        if rate_map is None or inv.base_currency not in rate_map or currency not in rate_map:
            raise ExchangeRateUnavailableError(currency)
        today = await settings_service.get_user_today(session, user_id)
    return _build_investment_metrics(inv, snapshots, transactions, currency, lookup, today)


# Computes portfolio-level metrics (total value, invested, gain, month change).
# When currency is provided, converts all monetary values via USD pivot.
async def get_portfolio_metrics(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    lookup: mh.RateLookup | None = None,
    investment_ids: list[int] | None = None,
    collection_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    today: date_type | None = None,
) -> PortfolioMetricsResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, collection_ids, category, search)
    # Build the lookup BEFORE the split so convertibility can check actual rate data presence.
    lookup = await _get_required_lookup(session, user_id, currency, all_investments, lookup)
    investments, skipped = _split_by_convertibility(all_investments, currency, lookup)
    if not investments:
        return PortfolioMetricsResponse(
            total_value=ZERO,
            total_invested=ZERO,
            absolute_gain=ZERO,
            currency=currency,
            skipped_investments=skipped,
        )

    inv_ids = [i.id for i in investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)
    # The user's own calendar day: what the portfolio is worth NOW converts at its rate, and the month
    # change compares it against the end of the month before it.
    if today is None:
        today = await settings_service.get_user_today(session, user_id)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)

    # Build a lookup from investment_id to base_currency.
    inv_currency = {i.id: i.base_currency for i in investments}

    # Per-investment {date: value} with each snapshot converted at its OWN date, so the return series
    # below (TWR, IRR, the flows a window counts) reflects what the portfolio actually looked like in
    # display currency at each point in time.
    inv_date_value: dict[int, dict[date_type, Decimal]] = {}
    for inv_id, snaps in snap_by_inv.items():
        dv: dict[date_type, Decimal] = {}
        base = inv_currency.get(inv_id, "")
        for s in snaps:
            v = s.value
            rate_map = _rate_map_at(lookup, s.date) if currency else None
            if currency and rate_map:
                converted = mh.convert_value(v, base, currency, rate_map)
                if converted is None:
                    continue
                v = converted
            dv[s.date] = v
        inv_date_value[inv_id] = dv
    first_snap_dates = {inv_id: min(dv) for inv_id, dv in inv_date_value.items() if dv}

    # Converted signed flows per investment (positive = money in, negative = money out), each
    # transaction converted at its own date.
    flows_by_inv: dict[int, list[tuple[date_type, Decimal]]] = {}
    for inv_id in inv_ids:
        base = inv_currency.get(inv_id, "")
        flows: list[tuple[date_type, Decimal]] = []
        for tx in tx_by_inv.get(inv_id, []):
            amount = tx.amount
            rate_map = _rate_map_at(lookup, tx.date) if currency else None
            if currency and rate_map:
                converted = mh.convert_value(amount, base, currency, rate_map)
                if converted is None:
                    continue
                amount = converted
            if tx.type in (TransactionType.deposit, TransactionType.buy):
                flows.append((tx.date, amount))
            else:
                flows.append((tx.date, -amount))
        flows_by_inv[inv_id] = flows

    # What the portfolio was worth on a day, for the return maths: what it held then (each holding's
    # last snapshot, carried forward however old) at THAT day's rate, plus the money moved in since each
    # holding's last snapshot, which no valuation has seen yet and counts at cost. Every point of the
    # series, both boundaries of a window and the month change are valued this one way, so the TWR, the
    # IRR and the gain all measure the same thing.
    def worth_on(day: date_type) -> Decimal:
        return _portfolio_value_on(snap_by_inv, inv_currency, currency, lookup, day, min(day, today)) + mh.flows_since_last_valuation(
            snap_by_inv, flows_by_inv, day
        )

    # The series the TWR chains and the windowed IRR closes on: one point per snapshot date.
    portfolio_totals = [(day, worth_on(day)) for day in sorted({s.date for snaps in snap_by_inv.values() for s in snaps})]

    # What the portfolio holds NOW — each investment's latest snapshot — at TODAY's rate: a holding is
    # worth what it would fetch today, so the headline, the allocation donuts and every per-holding
    # figure value it at the same rate the cash and card balances use. The gain maths end at `now_worth`,
    # which adds the money moved in since the last snapshots: a buy recorded today is held today, and
    # leaving it out read the deposit as a loss (and a sell as a gain) until the next snapshot.
    now_value = _sum_values(_convert_holdings(mh.holding_values_on(snap_by_inv, None), inv_currency, currency, lookup, today))
    now_worth = now_value + mh.flows_since_last_valuation(snap_by_inv, flows_by_inv, today)

    # Headline value/invested/gain: all-time without a window, period metrics with one
    # (value at window end, net flows inside the window, gain = end - start - net flows). A boundary is
    # a point in time, so it values what was held THEN at that day's rate — a window still open today
    # ends at the value now. The start also counts money moved in since the last snapshot before it:
    # that money was held on the start day, and leaving it out booked it as the window's gain and as
    # the first period's return.
    window_start_value = worth_on(start_date) if start_date else ZERO
    # Where the window closes: its end, or today while it is still open.
    if end_date and end_date < today:
        close_date, close_worth = end_date, worth_on(end_date)
    else:
        close_date, close_worth = today, now_worth
    if start_date or end_date:
        if end_date and end_date < today:
            window_end_value = _portfolio_value_on(snap_by_inv, inv_currency, currency, lookup, end_date, end_date)
        else:
            window_end_value = now_value
        window_net_flows = _net_flows_between(flows_by_inv, inv_date_value, first_snap_dates, start_date, end_date)
        total_value = window_end_value
        total_invested = window_net_flows
        absolute_gain = close_worth - window_start_value - window_net_flows
        # Period simple return over the capital at work (start value + contributed flows).
        denominator = window_start_value + window_net_flows
        total_return_pct = absolute_gain / denominator if denominator > ZERO else None
    else:
        total_value = now_value
        # Every flow, plus the opening value of a holding no flow explains (its first snapshot, at its
        # own date) — the capital it came in with.
        total_invested = sum((amount for flows in flows_by_inv.values() for _, amount in flows), ZERO)
        for inv_id in inv_ids:
            opening = mh.unexplained_opening(snap_by_inv.get(inv_id, []), tx_by_inv.get(inv_id, []))
            if opening is not None and opening.date in inv_date_value.get(inv_id, {}):
                total_invested += inv_date_value[inv_id][opening.date]
        absolute_gain = total_value - total_invested
        # Simple return is only meaningful when invested capital is positive.
        total_return_pct = None
        if total_invested > ZERO:
            total_return_pct = total_value / total_invested - ONE

    # Portfolio TWR: chain only the periods inside the requested window (every period without one), the
    # first running from the window start at the value held that day.
    portfolio_twr = mh.windowed_twr(
        portfolio_totals, inv_date_value, flows_by_inv, start_date, end_date, window_start_value, end_point=(close_date, close_worth)
    )

    # What the portfolio GAINED since the end of last month — the period gain of a window opening then
    # and still open today: the value now, less what was held at the end of last month (valued at that
    # day's rate, plus money moved in since its last snapshot), less the money moved in since. Not the
    # change in value, which reads a deposit as gain. The percentage is over the capital at work (what
    # was held plus what came in), as a window's is. Null when nothing was held by then (there is
    # nothing to compare against).
    month_change = None
    month_change_pct = None
    prev_end = mh.previous_month_end(today)
    prev_values = mh.holding_values_on(snap_by_inv, prev_end)
    if prev_values:
        prev_total = worth_on(prev_end)
        month_flows = _net_flows_between(flows_by_inv, inv_date_value, first_snap_dates, prev_end, None)
        month_change = now_worth - prev_total - month_flows
        capital = prev_total + month_flows
        if capital > ZERO:
            month_change_pct = month_change / capital

    # Portfolio IRR: combined cashflow series across all investments, each cashflow converted at
    # its own date. With a window, boundary valuations from the totals series replace the raw
    # flows outside it.
    all_cashflows: list[tuple[date_type, float]]
    if start_date or end_date:
        all_cashflows = mh.build_windowed_portfolio_cashflows(
            portfolio_totals,
            inv_date_value,
            flows_by_inv,
            start_date,
            end_date,
            start_value=window_start_value if start_date else None,
            end_point=(close_date, close_worth),
        )
    else:
        all_cashflows = []
        for inv_id in inv_ids:
            snaps = snap_by_inv.get(inv_id, [])
            txs = tx_by_inv.get(inv_id, [])
            cfs = mh.build_irr_cashflows(snaps, txs)
            base = inv_currency.get(inv_id, "")
            if currency and lookup:
                converted_cfs: list[tuple[date_type, float]] = []
                for d, a in cfs:
                    rate_map = lookup.get_rate_map_at(d)
                    amount = mh.convert_value(Decimal(str(a)), base, currency, rate_map) if rate_map else None
                    if amount is None:
                        continue
                    converted_cfs.append((d, float(amount)))
                cfs = converted_cfs
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
#
# Every point is a point in time, so it values what was held THEN at that month's rate — its month end,
# or today's rate for the current month (no rate is stored past today) — including a holding carried
# forward from an older snapshot: the carried value converts at the point's rate, not at its snapshot's.
# Converting the carried value at the snapshot's rate froze it in display currency for as long as no new
# snapshot arrived, so the chart's last point drifted from the headline, which values the same holdings
# at today's rate. With `today`, the series runs on to the current month, so its last point is the
# headline's own figure; without one (no display currency requested, where nothing converts) it ends at
# the latest snapshot's month as before.
async def get_portfolio_evolution(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    lookup: mh.RateLookup | None = None,
    investment_ids: list[int] | None = None,
    collection_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    today: date_type | None = None,
) -> PortfolioEvolutionResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, collection_ids, category, search)
    # Build the lookup BEFORE the split so convertibility can check actual rate data presence.
    lookup = await _get_required_lookup(session, user_id, currency, all_investments, lookup)
    investments, skipped = _split_by_convertibility(all_investments, currency, lookup)
    if not investments:
        return PortfolioEvolutionResponse(points=[], currency=currency, skipped_investments=skipped)

    inv_ids = [i.id for i in investments]
    inv_currency = {i.id: i.base_currency for i in investments}

    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    if not snap_by_inv:
        return PortfolioEvolutionResponse(points=[], currency=currency, skipped_investments=skipped)
    if today is None and currency:
        today = await settings_service.get_user_today(session, user_id)

    # Each investment's value per month (first of month): the last snapshot dated in that month.
    inv_month_value: dict[int, dict[date_type, Decimal]] = {}
    for inv_id, snaps in snap_by_inv.items():
        month_map: dict[date_type, Decimal] = {}
        for s in snaps:
            month_map[date_type(s.date.year, s.date.month, 1)] = s.value
        inv_month_value[inv_id] = month_map

    # Every month from the earliest snapshot to the latest one, or to the current month when later.
    min_date = min(s.date for snaps in snap_by_inv.values() for s in snaps)
    max_date = max(s.date for snaps in snap_by_inv.values() for s in snaps)
    if today is not None and today > max_date:
        max_date = today
    all_months: list[date_type] = []
    cursor = date_type(min_date.year, min_date.month, 1)
    end = date_type(max_date.year, max_date.month, 1)
    while cursor <= end:
        all_months.append(cursor)
        if cursor.month == 12:
            cursor = date_type(cursor.year + 1, 1, 1)
        else:
            cursor = date_type(cursor.year, cursor.month + 1, 1)

    # For each month, sum values across investments (forward-fill missing months), each converted at
    # the month's own rate.
    points: list[EvolutionPoint] = []
    last_known: dict[int, Decimal] = {}
    for month in all_months:
        for inv_id in inv_ids:
            month_map = inv_month_value.get(inv_id, {})
            if month in month_map:
                last_known[inv_id] = month_map[month]
        rate_date = date_type(month.year, month.month, _calendar.monthrange(month.year, month.month)[1])
        total = _sum_values(_convert_holdings(last_known, inv_currency, currency, lookup, rate_date))
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
    lookup: mh.RateLookup | None = None,
    investment_ids: list[int] | None = None,
    collection_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    today: date_type | None = None,
) -> AllocationResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, collection_ids, category, search)
    # Build the lookup BEFORE the split so convertibility can check actual rate data presence.
    lookup = await _get_required_lookup(session, user_id, currency, all_investments, lookup)
    investments, skipped = _split_by_convertibility(all_investments, currency, lookup)
    if not investments:
        return AllocationResponse(items=[], total_value=ZERO, skipped_investments=skipped)

    inv_ids = [i.id for i in investments]
    latest_map = await metrics_repository.get_latest_snapshots(session, inv_ids)
    values = await _current_values(session, user_id, latest_map, {i.id: i.base_currency for i in investments}, currency, lookup, today)

    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for inv in investments:
        if inv.id in values:
            cat_values[inv.category] += values[inv.id]

    total_value = sum(cat_values.values(), ZERO)

    items = []
    for category, value in sorted(cat_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_value * 100) if total_value != ZERO else ZERO
        items.append(AllocationItem(category=category, value=value, percentage=pct))

    return AllocationResponse(items=items, total_value=total_value, skipped_investments=skipped)


# Computes allocation by investment collection.
# Investments not in any collection are bucketed under "Unassigned".
async def get_allocation_by_collection(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    collection_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
) -> CollectionAllocationResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, collection_ids, category, search)
    # Build the lookup BEFORE the split so convertibility can check actual rate data presence.
    lookup = await _get_required_lookup(session, user_id, currency, all_investments)
    investments, skipped = _split_by_convertibility(all_investments, currency, lookup)
    if not investments:
        return CollectionAllocationResponse(items=[], total_value=ZERO, skipped_investments=skipped)

    inv_ids = [i.id for i in investments]
    inv_currency = {i.id: i.base_currency for i in investments}
    latest_map = await metrics_repository.get_latest_snapshots(session, inv_ids)

    # Build {investment_id: converted_value} for investments with snapshots, at today's rate.
    inv_values = await _current_values(session, user_id, latest_map, inv_currency, currency, lookup, None)

    # Load collections and their memberships — batch query.
    collections = await collection_repository.list_by_user(session, user_id, limit=MAX_LIST_ROWS)
    all_collection_ids = [c.id for c in collections if c.id is not None]
    ids_by_collection = await collection_repository.get_investment_ids_by_collections(session, all_collection_ids)
    assigned_inv_ids: set[int] = set()
    collection_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    collection_targets: dict[str, Decimal | None] = {}

    for collection in collections:
        collection_targets[collection.name] = collection.target_percentage
        for mid in ids_by_collection.get(collection.id, []):
            if mid in inv_values:
                collection_values[collection.name] += inv_values[mid]
                assigned_inv_ids.add(mid)

    # Unassigned bucket.
    unassigned = ZERO
    for inv_id, val in inv_values.items():
        if inv_id not in assigned_inv_ids:
            unassigned += val
    if unassigned > ZERO:
        collection_values["Unassigned"] = unassigned

    # The base is the portfolio itself — every investment once — not the sum of the buckets: an
    # investment can sit in several collections, and summing the buckets counted it once per collection,
    # shrinking every share and every comparison with a target. Each share is therefore "this much of
    # the portfolio is in this collection", and overlapping collections can add up to more than 100%.
    total_value = sum(inv_values.values(), ZERO)

    items = []
    for name, value in sorted(collection_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_value * 100) if total_value != ZERO else ZERO
        target = collection_targets.get(name)
        diff = pct - target if target is not None else None
        items.append(
            CollectionAllocationItem(
                collection_name=name,
                value=value,
                percentage=pct,
                target_percentage=target,
                difference=diff,
            )
        )

    return CollectionAllocationResponse(items=items, total_value=total_value, skipped_investments=skipped)


# Computes lightweight per-investment metrics for the dashboard compact table.
# Returns current value, invested capital, absolute gain, and month-over-month change.
async def get_investments_summary(
    session: AsyncSession,
    user_id: int,
    currency: str | None = None,
    investment_ids: list[int] | None = None,
    collection_ids: list[int] | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> InvestmentsSummaryResponse:
    all_investments = await _resolve_filtered_investments(session, user_id, investment_ids, collection_ids, category, search)
    # Build the lookup BEFORE the split so convertibility can check actual rate data presence.
    lookup = await _get_required_lookup(session, user_id, currency, all_investments)
    investments, skipped = _split_by_convertibility(all_investments, currency, lookup)
    if not investments:
        return InvestmentsSummaryResponse(items=[], skipped_investments=skipped)

    inv_ids = [i.id for i in investments]

    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)
    # The user's own calendar day: each holding's current value converts at its rate, and its month
    # change compares it against the end of the month before.
    today = await settings_service.get_user_today(session, user_id)
    prev_end = mh.previous_month_end(today)
    inv_currency = {i.id: i.base_currency for i in investments}
    now_values = _convert_holdings(mh.holding_values_on(snap_by_inv, None), inv_currency, currency, lookup, today)
    prev_values = _convert_holdings(mh.holding_values_on(snap_by_inv, prev_end), inv_currency, currency, lookup, prev_end)

    items: list[InvestmentSummaryItem] = []
    for inv in investments:
        snaps = snap_by_inv.get(inv.id, [])
        txs = tx_by_inv.get(inv.id, [])
        base = inv.base_currency

        # Check if the investment has any snapshots within the selected date range.
        has_snapshots_in_period = True
        if start_date or end_date:
            has_snapshots_in_period = any((start_date is None or s.date >= start_date) and (end_date is None or s.date <= end_date) for s in snaps)

        latest_snap = snaps[-1] if snaps else None
        current_value = latest_snap.value if latest_snap else None
        # Signed flows, each converted at its own date (positive = money in), plus the opening value of a
        # holding no flow explains — the capital it came in with, at its first snapshot's date.
        flows = _signed_flows(txs, base, currency, lookup)
        opening = mh.unexplained_opening(snaps, txs)
        cap = mh.invested_capital(txs) + (opening.value if opening else ZERO)
        absolute_gain = (current_value - cap) if current_value is not None else None

        # What the holding gained since the end of last month, consistent with the portfolio card: the
        # value now, less what it was worth then (at that day's rate), less the money moved in since —
        # over the capital at work. Both ends count money moved in since the last snapshot before them,
        # so a buy not yet snapshotted reads neither as a loss nor as a gain. Null for a holding not yet
        # valued by then.
        month_change_pct = None
        prev_v = prev_values.get(inv.id)
        curr_v = now_values.get(inv.id)
        if prev_v is not None and curr_v is not None:
            prev_v += mh.flows_since_last_valuation({inv.id: snaps}, {inv.id: flows}, prev_end)
            curr_v += mh.flows_since_last_valuation({inv.id: snaps}, {inv.id: flows}, today)
            month_flows = sum((amount for d, amount in flows if d > prev_end), ZERO)
            capital = prev_v + month_flows
            if capital > ZERO:
                month_change_pct = (curr_v - capital) / capital

        # Convert absolute values — current_value at today's rate (what it is worth now), cap as a sum
        # of per-transaction conversions at each tx's own date.
        if currency and lookup:
            if current_value is not None:
                current_value = now_values.get(inv.id)
            cap = sum((amount for _, amount in flows), ZERO) + _opening_in(opening, base, currency, lookup)
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


# What each investment holds now — its latest snapshot — converted at TODAY's rate (the user's own
# calendar day, resolved here when the caller has not already). Returns {investment_id: value}.
async def _current_values(
    session: AsyncSession,
    user_id: int,
    latest_map: dict[int, InvestmentSnapshot],
    inv_currency: dict[int, str],
    currency: str | None,
    lookup: mh.RateLookup | None,
    today: date_type | None,
) -> dict[int, Decimal]:
    values = {inv_id: snapshot.value for inv_id, snapshot in latest_map.items()}
    if not currency:
        return values
    if today is None:
        today = await settings_service.get_user_today(session, user_id)
    return _convert_holdings(values, inv_currency, currency, lookup, today)


# Returns a RateLookup pre-loaded with every stored rate (Phase 3, Step C — date-aware conversion).
# Callers look up per-row dates via lookup.get_rate_map_at(...). Raises ExchangeRateUnavailableError
# if conversion is needed but the rates table is empty. Returns None when currency is None or no
# conversion is needed at all. Reuses a prebuilt per-request lookup when the caller already built one.
async def _get_required_lookup(
    session: AsyncSession,
    user_id: int,
    currency: str | None,
    investments: list[Investment],
    lookup: mh.RateLookup | None = None,
) -> mh.RateLookup | None:
    if not currency:
        return None
    needs_conversion = any(inv.base_currency != currency for inv in investments)
    if not needs_conversion:
        return None
    if lookup is None:
        lookup = await exchange_rate_service.get_user_rate_lookup(session, user_id)
    # Probe date is irrelevant here: get_rate_map_at returns None only when the rates table is
    # empty, so the server-local today is fine (no user-timezone read needed for this check).
    if lookup.get_rate_map_at(date_type.today()) is None:
        raise ExchangeRateUnavailableError(currency)
    return lookup


# Convenience: returns the rate map at as_of_date through the given lookup, or None when lookup is None.
def _rate_map_at(lookup: mh.RateLookup | None, as_of_date: date_type) -> dict[str, Decimal] | None:
    if lookup is None:
        return None
    return lookup.get_rate_map_at(as_of_date)


# An investment's transactions as signed flows (positive = money in), each converted into the display
# currency at its own date. A transaction that cannot convert is left out — the investment itself is
# only reached once its currency is known to convert. Unconverted without a display currency.
def _signed_flows(
    transactions: list[Transaction],
    base: str,
    currency: str | None,
    lookup: mh.RateLookup | None,
) -> list[tuple[date_type, Decimal]]:
    flows: list[tuple[date_type, Decimal]] = []
    for tx in transactions:
        amount: Decimal | None = tx.amount
        if currency and lookup:
            rate_map = lookup.get_rate_map_at(tx.date)
            amount = mh.convert_value(tx.amount, base, currency, rate_map) if rate_map else None
            if amount is None:
                continue
        flows.append((tx.date, amount if tx.type in (TransactionType.deposit, TransactionType.buy) else -amount))
    return flows


# An unexplained opening's value in the display currency, at its own date — ZERO when there is none or it
# cannot convert.
def _opening_in(
    opening: InvestmentSnapshot | None,
    base: str,
    currency: str | None,
    lookup: mh.RateLookup | None,
) -> Decimal:
    if opening is None:
        return ZERO
    if not (currency and lookup):
        return opening.value
    rate_map = lookup.get_rate_map_at(opening.date)
    converted = mh.convert_value(opening.value, base, currency, rate_map) if rate_map else None
    return converted if converted is not None else ZERO


# The net money that entered the portfolio inside the window (after, until] — either bound may be None:
# real flows after each investment's first snapshot (one on or before it is embodied in that value),
# plus the first snapshot itself of an investment born inside the window (contributed capital).
# flows_by_inv and inv_date_value are already in the display currency, each at its own date.
def _net_flows_between(
    flows_by_inv: dict[int, list[tuple[date_type, Decimal]]],
    inv_date_value: dict[int, dict[date_type, Decimal]],
    first_snap_dates: dict[int, date_type],
    after: date_type | None,
    until: date_type | None,
) -> Decimal:
    total = ZERO
    for inv_id, flows in flows_by_inv.items():
        first_date = first_snap_dates.get(inv_id)
        for flow_date, amount in flows:
            if first_date is not None and flow_date <= first_date:
                continue
            if after and flow_date <= after:
                continue
            if until and flow_date > until:
                continue
            total += amount
    for inv_id, first_date in first_snap_dates.items():
        if after and first_date <= after:
            continue
        if until and first_date > until:
            continue
        total += inv_date_value[inv_id][first_date]
    return total


# Converts each investment's base-currency value into the display currency at the rate of rate_date —
# the day the figure is ABOUT: today for what is held now, a point's own date for a point in the past.
# Each holding converts on its own, so the per-holding figures, the allocation buckets and the totals
# they add up to round identically. Returns {investment_id: value}, without an investment that cannot
# convert (the caller has already reported it skipped); unchanged values when no currency is requested.
def _convert_holdings(
    values: dict[int, Decimal],
    inv_currency: dict[int, str],
    currency: str | None,
    lookup: mh.RateLookup | None,
    rate_date: date_type,
) -> dict[int, Decimal]:
    if not currency:
        return dict(values)
    rate_map = _rate_map_at(lookup, rate_date)
    converted: dict[int, Decimal] = {}
    for inv_id, value in values.items():
        base = inv_currency.get(inv_id, "")
        if base == currency:
            converted[inv_id] = value
            continue
        amount = mh.convert_value(value, base, currency, rate_map) if rate_map else None
        if amount is not None:
            converted[inv_id] = amount
    return converted


# The portfolio held on as_of_date (each investment's last snapshot on or before it), valued at the rate
# of rate_date and summed.
def _portfolio_value_on(
    snap_by_inv: dict[int, list[InvestmentSnapshot]],
    inv_currency: dict[int, str],
    currency: str | None,
    lookup: mh.RateLookup | None,
    as_of_date: date_type,
    rate_date: date_type,
) -> Decimal:
    return _sum_values(_convert_holdings(mh.holding_values_on(snap_by_inv, as_of_date), inv_currency, currency, lookup, rate_date))


# Sums a {investment_id: value} map.
def _sum_values(values: dict[int, Decimal]) -> Decimal:
    return sum(values.values(), ZERO)


# Builds InvestmentMetricsResponse from raw data.
# When currency and lookup are provided, converts absolute values via USD pivot — current_value at
# today's rate (what the holding is worth now), cap as a per-transaction sum at each one's own date,
# and each period_return point at its own date.
def _build_investment_metrics(
    investment: Investment,
    snapshots: list[InvestmentSnapshot],
    transactions: list[Transaction],
    currency: str | None = None,
    lookup: mh.RateLookup | None = None,
    today: date_type | None = None,
) -> InvestmentMetricsResponse:
    # Capital in: every flow, plus the opening value of a holding no flow explains.
    opening = mh.unexplained_opening(snapshots, transactions)
    cap = mh.invested_capital(transactions) + (opening.value if opening else ZERO)
    latest_snap = snapshots[-1] if snapshots else None
    current_value = latest_snap.value if latest_snap else None
    absolute_gain = (current_value - cap) if current_value is not None else None

    # Simple return is only meaningful when invested capital is positive (mirrors portfolio level).
    simple_return = None
    if current_value is not None and cap > ZERO:
        simple_return = current_value / cap - ONE

    # Period returns.
    pr_data = mh.compute_period_returns(snapshots, transactions)

    # TWR: chain valid period returns.
    valid_returns = [r for _, _, r in pr_data if r is not None]
    twr_val = mh.twr(valid_returns)

    # IRR: annualised money-weighted return — convert each cashflow at its own date.
    base = investment.base_currency
    irr_cashflows = mh.build_irr_cashflows(snapshots, transactions)
    if currency and lookup:
        converted_irr: list[tuple[date_type, float]] = []
        for d, a in irr_cashflows:
            rate_map = lookup.get_rate_map_at(d)
            amount = mh.convert_value(Decimal(str(a)), base, currency, rate_map) if rate_map else None
            # Defensive: unreachable after the pair-presence gate above.
            if amount is None:
                continue
            converted_irr.append((d, float(amount)))
        irr_cashflows = converted_irr
    irr_val = mh.xirr(irr_cashflows)

    # Convert absolute values if currency requested — the current value at today's rate (what the
    # holding is worth now), the capital per transaction at each one's own date.
    if currency and lookup:
        if current_value is not None and latest_snap is not None:
            rate_map = lookup.get_rate_map_at(today or latest_snap.date)
            if rate_map:
                current_value = mh.convert_value(current_value, base, currency, rate_map)
        converted_cap = _opening_in(opening, base, currency, lookup)
        for tx in transactions:
            rate_map = lookup.get_rate_map_at(tx.date)
            amount = mh.convert_value(tx.amount, base, currency, rate_map) if rate_map else None
            if amount is None:
                continue
            if tx.type in (TransactionType.deposit, TransactionType.buy):
                converted_cap += amount
            else:
                converted_cap -= amount
        cap = converted_cap
        absolute_gain = (current_value - cap) if current_value is not None else None

    period_returns: list[PeriodReturnItem] = []
    for d, v, r in pr_data:
        converted_v = v
        if currency and lookup:
            rate_map = lookup.get_rate_map_at(d)
            if rate_map:
                converted = mh.convert_value(v, base, currency, rate_map)
                if converted is None:
                    continue
                converted_v = converted
        period_returns.append(PeriodReturnItem(date=d, value=converted_v, return_pct=r))

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
