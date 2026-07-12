# Business logic for building the snapshots grid (investments × months).

from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ExchangeRateUnavailableError
from app.models.investment import InvestmentCategory
from app.repositories.cedear_ratio_repository import cedear_ratio_repository
from app.repositories.metrics_repository import metrics_repository
from app.schemas.snapshot_grid import (
    SnapshotGridCell,
    SnapshotGridResponse,
    SnapshotGridRow,
    SnapshotGridTransaction,
)
from app.services import exchange_rate_service
from app.utils import metrics as mh


# Builds the snapshots grid for a user's investments.
# Returns rows (investments) with snapshot cells, period returns, and transaction details.
# When currency is provided, converts cell values via USD pivot.
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

    lookup: mh.RateLookup | None = None
    if currency:
        needs_conversion = any(inv.base_currency != currency for inv in investments)
        if needs_conversion:
            lookup = await exchange_rate_service.get_user_rate_lookup(session, user_id)
            if lookup.get_rate_map_at(date_type.today()) is None:
                raise ExchangeRateUnavailableError(currency)
    inv_ids = [i.id for i in investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)

    # Collect all unique dates.
    all_dates = sorted({s.date for s in all_snapshots})

    # Batch-load CEDEAR ratios for CEDEAR investments.
    cedear_tickers = [inv.ticker for inv in investments if inv.ticker and inv.category == InvestmentCategory.cedears]
    cedear_ratios = await cedear_ratio_repository.get_latest_by_tickers(session, cedear_tickers)

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
            # Per-snapshot conversion at the snapshot's own date (Phase 3, Step C). Each historical
            # cell stays deterministic across time — re-opening tomorrow shows the same number.
            snap_rate_map = lookup.get_rate_map_at(snap.date) if currency and lookup else None
            if snap_rate_map:
                value = mh.convert_value(value, inv.base_currency, currency, snap_rate_map)
            # Transactions get converted at their own date, not the snapshot's, since a transaction
            # may occur on any day within the snapshot period.
            tx_amount = tx.amount if tx else None
            if tx is not None and currency and lookup:
                tx_rate_map = lookup.get_rate_map_at(tx.date)
                if tx_rate_map:
                    tx_amount = mh.convert_value(tx.amount, inv.base_currency, currency, tx_rate_map)
            cells.append(
                SnapshotGridCell(
                    date=snap.date,
                    value=value,
                    original_value=snap.value,
                    quantity=snap.quantity,
                    source=snap.source,
                    period_return_pct=pr_map.get(snap.date),
                    has_transaction=tx is not None,
                    transaction=SnapshotGridTransaction(
                        id=tx.id,
                        amount=tx_amount if tx_amount is not None else tx.amount,
                        original_amount=tx.amount,
                        quantity=tx.quantity,
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
                ticker=inv.ticker,
                cedear_ratio=cedear_ratios.get(inv.ticker) if inv.ticker else None,
                cells=cells,
            )
        )

    return SnapshotGridResponse(rows=rows, months=all_dates)


# Returns {snapshot_date: latest_transaction} for periods that had transactions.
# The first snapshot maps transactions on or before its date.
# Subsequent snapshots map transactions between (prev_date, curr_date].
def _build_transaction_period_map(snaps, txs):
    if not snaps or not txs:
        return {}

    result = {}

    # First snapshot: latest transaction on or before its date.
    first_date = snaps[0].date
    candidates = [tx for tx in txs if tx.date <= first_date]
    if candidates:
        result[first_date] = max(candidates, key=lambda t: t.date)

    # Subsequent snapshots: latest transaction between (prev_date, curr_date].
    for i in range(1, len(snaps)):
        prev_date = snaps[i - 1].date
        curr_date = snaps[i].date
        candidates = [tx for tx in txs if prev_date < tx.date <= curr_date]
        if candidates:
            result[curr_date] = max(candidates, key=lambda t: t.date)
    return result
