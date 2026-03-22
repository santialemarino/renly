# Business logic for building the snapshots grid (investments × months).

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange_rate import ExchangeRatePair
from app.models.investment import InvestmentCategory
from app.repositories.exchange_rate_repository import exchange_rate_repository
from app.repositories.metrics_repository import metrics_repository
from app.schemas.snapshot_grid import (
    SnapshotGridCell,
    SnapshotGridResponse,
    SnapshotGridRow,
    SnapshotGridTransaction,
)
from app.services import metrics_helpers as mh


# Builds the snapshots grid for a user's investments.
# Returns rows (investments) with snapshot cells, period returns, and transaction details.
# When currency is provided, converts cell values using the latest MEP rate.
async def get_snapshot_grid(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    group_ids: list[int] | None = None,
    category: InvestmentCategory | None = None,
    currency: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> SnapshotGridResponse:
    investments = await metrics_repository.list_active_investments(session, user_id)

    # Apply filters in memory (small dataset: 2-3 users, ~20 investments).
    if search:
        q = search.lower()
        investments = [i for i in investments if q in i.name.lower()]
    if category:
        investments = [i for i in investments if i.category == category]
    if group_ids:
        from app.repositories.investment_repository import investment_repository

        groups_map = await investment_repository.get_groups_by_investment_ids(session, [i.id for i in investments])
        group_set = set(group_ids)
        investments = [i for i in investments if any(gid in group_set for gid, _ in groups_map.get(i.id, []))]

    # Sort.
    if sort_by == "name":
        investments = sorted(investments, key=lambda i: i.name.lower(), reverse=sort_order == "desc")

    if not investments:
        return SnapshotGridResponse(rows=[], months=[])

    rate = await _get_conversion_rate(session) if currency else None
    inv_ids = [i.id for i in investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)

    # Collect all unique dates.
    all_dates = sorted({s.date for s in all_snapshots})

    rows: list[SnapshotGridRow] = []
    for inv in investments:
        snaps = snap_by_inv.get(inv.id, [])
        txs = tx_by_inv.get(inv.id, [])

        # Compute period returns for this investment.
        pr_data = mh.compute_period_returns(snaps, txs)
        pr_map = {d: r for d, _, r in pr_data}

        # Build transaction lookup: snapshot date → latest transaction in that period.
        tx_by_period = _build_transaction_period_map(snaps, txs)

        cells: list[SnapshotGridCell] = []
        for snap in snaps:
            tx = tx_by_period.get(snap.date)
            value = snap.value
            if currency and rate:
                value = mh.convert_value(value, inv.base_currency, currency, rate)
            cells.append(
                SnapshotGridCell(
                    date=snap.date,
                    value=value,
                    period_return_pct=pr_map.get(snap.date),
                    has_transaction=tx is not None,
                    transaction=SnapshotGridTransaction(
                        id=tx.id,
                        amount=tx.amount,
                        type=tx.type,
                    )
                    if tx
                    else None,
                )
            )

        rows.append(
            SnapshotGridRow(
                investment_id=inv.id,
                name=inv.name,
                category=inv.category,
                base_currency=inv.base_currency,
                cells=cells,
            )
        )

    return SnapshotGridResponse(rows=rows, months=all_dates)


# Returns the latest USD/ARS MEP rate. Falls back to oficial if MEP unavailable.
async def _get_conversion_rate(session: AsyncSession) -> Decimal | None:
    latest_map = await exchange_rate_repository.get_latest_all(session)
    mep = latest_map.get(ExchangeRatePair.USD_ARS_MEP)
    if mep:
        return mep.rate
    oficial = latest_map.get(ExchangeRatePair.USD_ARS_OFICIAL)
    if oficial:
        return oficial.rate
    return None


# Returns {snapshot_date: latest_transaction} for periods that had transactions.
def _build_transaction_period_map(snaps, txs):
    if not snaps or not txs:
        return {}

    result = {}
    for i in range(1, len(snaps)):
        prev_date = snaps[i - 1].date
        curr_date = snaps[i].date
        latest_tx = None
        for tx in txs:
            if prev_date < tx.date <= curr_date:
                if latest_tx is None or tx.date > latest_tx.date:
                    latest_tx = tx
        if latest_tx:
            result[curr_date] = latest_tx
    return result
