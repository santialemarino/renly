# Business logic for investment and portfolio metrics.

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.investment import Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
from app.repositories.investment_repository import investment_repository
from app.repositories.metrics_repository import metrics_repository
from app.schemas.metrics import (
    AllocationItem,
    AllocationResponse,
    InvestmentMetricsResponse,
    PeriodReturnItem,
    PortfolioMetricsResponse,
)
from app.services import metrics_helpers as mh

ZERO = Decimal("0")
ONE = Decimal("1")


# Computes metrics for a single investment (TWR, IRR, period returns, etc.).
async def get_investment_metrics(
    session: AsyncSession,
    investment_id: int,
    user_id: int,
) -> InvestmentMetricsResponse:
    inv = await investment_repository.get_by_id(session, investment_id, user_id)
    if inv is None:
        raise NotFoundError(f"Investment {investment_id} not found.")

    snapshots = await metrics_repository.list_snapshots_by_investments(session, [investment_id])
    transactions = await metrics_repository.list_transactions_by_investments(session, [investment_id])

    return _build_investment_metrics(inv, snapshots, transactions)


# Computes portfolio-level metrics (total value, invested, gain, month change).
async def get_portfolio_metrics(
    session: AsyncSession,
    user_id: int,
) -> PortfolioMetricsResponse:
    investments = await metrics_repository.list_active_investments(session, user_id)
    if not investments:
        return PortfolioMetricsResponse(
            total_value=ZERO,
            total_invested=ZERO,
            absolute_gain=ZERO,
        )

    inv_ids = [i.id for i in investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    # Group by investment; derive latest snapshot from the grouped result (avoids extra query).
    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    latest_map = {inv_id: snaps[-1] for inv_id, snaps in snap_by_inv.items()}

    # Total current value.
    total_value = sum((s.value for s in latest_map.values()), ZERO)

    # Total invested capital.
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)
    total_invested = ZERO
    for inv_id in inv_ids:
        total_invested += mh.invested_capital(tx_by_inv.get(inv_id, []))

    absolute_gain = total_value - total_invested

    total_return_pct = None
    if total_invested != ZERO:
        total_return_pct = total_value / total_invested - ONE

    # Month-over-month change: only compare investments that have both a current and previous
    # snapshot, so the two totals cover the same set of investments.
    curr_for_change = ZERO
    prev_total = ZERO
    has_prev = False
    for inv_id in inv_ids:
        snaps = snap_by_inv.get(inv_id, [])
        if len(snaps) >= 2:
            curr_for_change += snaps[-1].value
            prev_total += snaps[-2].value
            has_prev = True

    month_change = (curr_for_change - prev_total) if has_prev else None
    month_change_pct = None
    if has_prev and prev_total != ZERO:
        month_change_pct = (curr_for_change - prev_total) / prev_total

    # Currency is reported only when all investments share the same base_currency.
    currencies = {i.base_currency for i in investments if i.id in latest_map}
    currency = currencies.pop() if len(currencies) == 1 else None

    return PortfolioMetricsResponse(
        total_value=total_value,
        total_invested=total_invested,
        absolute_gain=absolute_gain,
        total_return_pct=total_return_pct,
        month_change=month_change,
        month_change_pct=month_change_pct,
        currency=currency,
    )


# Computes allocation by investment category.
async def get_allocation(
    session: AsyncSession,
    user_id: int,
) -> AllocationResponse:
    investments = await metrics_repository.list_active_investments(session, user_id)
    if not investments:
        return AllocationResponse(items=[], total_value=ZERO)

    inv_ids = [i.id for i in investments]
    latest_map = await metrics_repository.get_latest_snapshots(session, inv_ids)

    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for inv in investments:
        snapshot = latest_map.get(inv.id)
        if snapshot:
            cat_values[inv.category] += snapshot.value

    total_value = sum(cat_values.values(), ZERO)

    items = []
    for category, value in sorted(cat_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_value * 100) if total_value != ZERO else ZERO
        items.append(AllocationItem(category=category, value=value, percentage=pct))

    return AllocationResponse(items=items, total_value=total_value)


# Builds InvestmentMetricsResponse from raw data.
def _build_investment_metrics(
    investment: Investment,
    snapshots: list[InvestmentSnapshot],
    transactions: list[Transaction],
) -> InvestmentMetricsResponse:
    cap = mh.invested_capital(transactions)
    current_value = snapshots[-1].value if snapshots else None
    absolute_gain = (current_value - cap) if current_value is not None else None

    simple_return = None
    if current_value is not None and cap != ZERO:
        simple_return = current_value / cap - ONE

    # Period returns.
    pr_data = mh.compute_period_returns(snapshots, transactions)
    period_returns = [PeriodReturnItem(date=d, value=v, return_pct=r) for d, v, r in pr_data]

    # TWR: chain valid period returns.
    valid_returns = [r for _, _, r in pr_data if r is not None]
    twr_val = mh.twr(valid_returns)

    # IRR: annualised money-weighted return.
    irr_cashflows = mh.build_irr_cashflows(snapshots, transactions)
    irr_val = mh.xirr(irr_cashflows)

    return InvestmentMetricsResponse(
        investment_id=investment.id,
        name=investment.name,
        category=investment.category,
        base_currency=investment.base_currency,
        current_value=current_value,
        invested_capital=cap,
        absolute_gain=absolute_gain,
        simple_return=simple_return,
        twr=twr_val,
        irr=irr_val,
        period_returns=period_returns,
    )
