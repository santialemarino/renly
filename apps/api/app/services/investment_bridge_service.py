# Business logic for the investment-to-finance bridge.
# Computes monthly investment returns and creates income entries with
# category='investment_returns' and source='auto', so investment gains
# appear in the financial dashboard automatically.

import logging
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.income_entry import IncomeCategory, IncomeEntry
from app.repositories.investment_repository import investment_repository
from app.repositories.metrics_repository import metrics_repository
from app.services.metrics_helpers import group_snapshots_by_investment, group_transactions_by_investment, net_cash_flow

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
SOURCE_AUTO = "auto"


# Generates income entries for monthly investment returns across all users.
# For each investment with at least two snapshots where the latest is from this month,
# computes the value delta adjusted for cash flows. Positive returns become income entries.
# Skips users who already have auto-generated investment_returns for today (idempotent).
# Returns the number of income entries created.
async def generate_investment_income(session: AsyncSession) -> int:
    today = date_type.today()

    # Batch-load all active investments, their snapshots, and transactions.
    all_investments = await investment_repository.list_active(session)
    if not all_investments:
        return 0

    inv_ids = [inv.id for inv in all_investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = group_snapshots_by_investment(all_snapshots)
    tx_by_inv = group_transactions_by_investment(all_transactions)

    # Skip users who already have bridge entries for today (idempotent re-runs).
    users_done = await _get_users_with_bridge_entries(session, today)

    # Compute returns and build income entries.
    entries: list[IncomeEntry] = []
    for inv in all_investments:
        if inv.user_id in users_done:
            continue

        snaps = snap_by_inv.get(inv.id, [])
        if len(snaps) < 2:
            continue

        # Use the two most recent snapshots for the monthly return.
        prev_snap = snaps[-2]
        curr_snap = snaps[-1]

        # Skip if the latest snapshot is not from the current month.
        if curr_snap.date.year != today.year or curr_snap.date.month != today.month:
            continue

        # Compute return: value delta adjusted for net cash flow.
        txs = tx_by_inv.get(inv.id, [])
        ncf = net_cash_flow(txs, prev_snap.date, curr_snap.date)
        monthly_return = curr_snap.value - prev_snap.value - ncf

        # Only record positive returns as income.
        if monthly_return <= ZERO:
            continue

        entries.append(
            IncomeEntry(
                user_id=inv.user_id,
                date=today,
                amount=monthly_return,
                currency=inv.base_currency,
                category=IncomeCategory.investment_returns,
                notes=f"Monthly return: {inv.name}",
                source=SOURCE_AUTO,
            )
        )

    if entries:
        session.add_all(entries)
        await session.commit()
        logger.info("Investment bridge: created %d income entries for %s.", len(entries), today)
    return len(entries)


# Returns the set of user IDs that already have auto-generated investment_returns
# income entries for the given date. Used for idempotent re-runs.
async def _get_users_with_bridge_entries(
    session: AsyncSession,
    bridge_date: date_type,
) -> set[int]:
    result = await session.execute(
        select(IncomeEntry.user_id)
        .where(
            IncomeEntry.date == bridge_date,
            IncomeEntry.source == SOURCE_AUTO,
            IncomeEntry.category == IncomeCategory.investment_returns,
        )
        .distinct()
    )
    return {row[0] for row in result.all()}
