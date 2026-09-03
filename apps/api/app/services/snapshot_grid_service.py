# Business logic for building the snapshots grid (investments × periods).
#
# X2 and X4 both land here. The grid is DUAL-SCOPE — a co-owned holding appears in its pot's own
# section, because snapshotting one is what keeps the pot valued at all and the grid is the fast way to
# do it — and its columns are weekly-CAPABLE, on a toolbar toggle rather than derived.
#
# ▸ Why a toggle and not a derived interval. §9 says a pot's cadence drives "the value-series columns on
# the pot page and in the grid", and on the pot page that is exact: one pot, one cadence, one grid. The
# snapshots grid is not one pot's series. It mixes private holdings (which declare no cadence at all)
# with the holdings of several pots that may each declare a different one, so there is no single derived
# answer — and deriving weekly from "any visible pot is weekly" would flip a user's whole grid to ~52
# columns because one of their pots is watched closely. The cadence still appears, as the per-row
# freshness indicator §8.2 asks for, which is where it belongs: a fact about one holding's valuation.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    ExchangeRateUnavailableError,
    PotSeriesInterval,
    is_valuation_overdue,
    period_end_containing,
    period_grid,
)
from app.domain.list_scope import SCOPE_PRIVATE, SCOPE_SHARED, ListScope, build_sections
from app.models.investment import Investment, InvestmentCategory
from app.repositories.cedear_ratio_repository import cedear_ratio_repository
from app.repositories.metrics_repository import metrics_repository
from app.schemas.metrics import SkippedInvestment
from app.schemas.snapshot_grid import (
    SnapshotGridCell,
    SnapshotGridResponse,
    SnapshotGridRow,
    SnapshotGridTransaction,
)
from app.services import exchange_rate_service, pot_service
from app.services.utils import pot_sections
from app.utils import metrics as mh

# How many columns the grid will draw, per interval. Two numbers rather than one because the intervals
# have genuinely different densities, and the monthly figure is deliberately beyond any real history
# (20 years) so the monthly grid keeps drawing its whole span exactly as it always has.
#
# The weekly cap is what makes weekly usable at all: a user snapshotting since 2020 has 68 monthly
# columns, which scrolls, and would have ~280 weekly ones — 5,600 cells for twenty rows, and unreadable
# besides. A year is the frame weekly monitoring is asked for in.
_MAX_MONTHLY_COLUMNS = 240
_MAX_WEEKLY_COLUMNS = 52


# The column cap that goes with an interval.
def _column_cap(interval: PotSeriesInterval) -> int:
    return _MAX_WEEKLY_COLUMNS if interval == PotSeriesInterval.weekly else _MAX_MONTHLY_COLUMNS


# Builds the snapshots grid for a user's investments.
# Returns rows (investments) with snapshot cells, period returns, and transaction details.
# When currency is provided, converts cell values via USD pivot.
async def get_snapshot_grid(
    session: AsyncSession,
    user_id: int,
    *,
    scope: ListScope = ListScope.private,
    interval: PotSeriesInterval = PotSeriesInterval.monthly,
    search: str | None = None,
    collection_ids: list[int] | None = None,
    category: InvestmentCategory | None = None,
    currency: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> SnapshotGridResponse:
    column_cap = _column_cap(interval)
    # The visible pots do three things from one read: they bound which pot rows the query may return,
    # they label the sections, and they carry the cadence each shared row's freshness is measured
    # against. A private-only request resolves none of it and costs what this grid cost before X2.
    scopes = [] if scope == ListScope.private else await pot_service.list_visible_scopes(session, user_id)
    pots_by_id = {s.pot_id: s for s in scopes}
    investments = await metrics_repository.list_active_investments(session, user_id, [s.pot_id for s in scopes], scope=scope)

    # Apply filters in memory (small dataset: 2-3 users, ~20 investments).
    if search:
        q = search.lower()
        investments = [i for i in investments if q in i.name.lower()]
    if category:
        investments = [i for i in investments if i.category == category]
    if collection_ids:
        from app.repositories.investment_repository import investment_repository

        collections_map = await investment_repository.get_collections_by_investment_ids(session, [i.id for i in investments])
        collection_set = set(collection_ids)
        investments = [i for i in investments if any(cid in collection_set for cid, _ in collections_map.get(i.id, []))]

    # Sort WITHIN each scope, which is what grouping a table means: the scope-major order the query
    # returned has to survive, or the sections stop being contiguous and their headers cannot be drawn.
    #
    # Two stable passes rather than one composite key, because `reverse=True` would reverse the SCOPE
    # order too and put the caller's own holdings last.
    if sort_by == "name":
        investments = sorted(investments, key=lambda i: i.name.lower(), reverse=sort_order == "desc")
        investments = sorted(investments, key=lambda i: (i.pot_id is not None, i.pot_id or 0))

    if not investments:
        return SnapshotGridResponse(rows=[], columns=[], interval=interval.value, sections=[], skipped_investments=[])

    lookup: mh.RateLookup | None = None
    skipped: list[SkippedInvestment] = []
    if currency:
        needs_conversion = any(inv.base_currency != currency for inv in investments)
        if needs_conversion:
            lookup = await exchange_rate_service.get_user_rate_lookup(session, user_id)
            # Server-local today is deliberate: this rate map only gates convertibility (empty-table
            # probe + per-pair membership below), where the <=1-day difference vs the user's local
            # date is immaterial — no user-timezone read needed. Cell values use each row's own date.
            rate_map_today = lookup.get_rate_map_at(date_type.today())
            if rate_map_today is None:
                raise ExchangeRateUnavailableError(currency)
            # Fail-loud: an investment whose pair has no stored rates is excluded and reported,
            # never rendered with unconverted cell values.
            convertible = []
            for inv in investments:
                if inv.base_currency == currency or (inv.base_currency in rate_map_today and currency in rate_map_today):
                    convertible.append(inv)
                else:
                    skipped.append(SkippedInvestment(investment_id=inv.id, name=inv.name, base_currency=inv.base_currency))
            investments = convertible
    inv_ids = [i.id for i in investments]
    all_snapshots = await metrics_repository.list_snapshots_by_investments(session, inv_ids)
    all_transactions = await metrics_repository.list_transactions_by_investments(session, inv_ids)

    snap_by_inv = mh.group_snapshots_by_investment(all_snapshots)
    tx_by_inv = mh.group_transactions_by_investment(all_transactions)

    # The columns span the DATA's own history, one period end per bucket with no gaps — a grid answers
    # "what has been recorded", not "the last N periods", which is the fixed-width question the pot
    # page's series asks and domain.period_ends answers.
    snapshot_dates = [s.date for s in all_snapshots]
    columns = period_grid(min(snapshot_dates), max(snapshot_dates), interval, limit=column_cap) if snapshot_dates else []

    # Batch-load CEDEAR ratios for CEDEAR investments.
    cedear_tickers = [inv.ticker for inv in investments if inv.ticker and inv.category == InvestmentCategory.cedears]
    cedear_ratios = await cedear_ratio_repository.get_latest_by_tickers(session, cedear_tickers)
    today = date_type.today()

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
                converted = mh.convert_value(value, inv.base_currency, currency, snap_rate_map)
                # Defensive: unreachable — inconvertible investments were filtered above.
                value = converted if converted is not None else value
            # Transactions get converted at their own date, not the snapshot's, since a transaction
            # may occur on any day within the snapshot period.
            tx_amount = tx.amount if tx else None
            if tx is not None and currency and lookup:
                tx_rate_map = lookup.get_rate_map_at(tx.date)
                if tx_rate_map:
                    converted_tx = mh.convert_value(tx.amount, inv.base_currency, currency, tx_rate_map)
                    # Defensive: unreachable — inconvertible investments were filtered above.
                    tx_amount = converted_tx if converted_tx is not None else tx.amount
            cells.append(
                SnapshotGridCell(
                    date=snap.date,
                    column=period_end_containing(snap.date, interval),
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

        rows.append(_build_row(inv, cells, cedear_ratios, pots_by_id, today=today))

    counts = [(inv.pot_id, None, None, 1) for inv in investments]
    return SnapshotGridResponse(
        rows=rows,
        columns=columns,
        interval=interval.value,
        sections=pot_sections(build_sections(counts), scopes) if scopes else [],
        skipped_investments=skipped,
    )


# One grid row, with the freshness the owning pot's cadence decides.
#
# The overdue question is asked through the SAME domain rule the pot page and the reminder job use, so a
# holding flagged behind here is behind everywhere. `holds_anything` is True by construction: this row
# exists because the investment does, and an investment nobody has ever valued IS behind by definition —
# its value cannot be stated at all, so no contribution can be priced against it.
def _build_row(
    inv: Investment,
    cells: list[SnapshotGridCell],
    cedear_ratios: dict[str, Decimal],
    pots_by_id: dict[int, pot_service.PotScope],
    *,
    today: date_type,
) -> SnapshotGridRow:
    cadence = pots_by_id[inv.pot_id].cadence if inv.pot_id is not None and inv.pot_id in pots_by_id else None
    valued_as_of = cells[-1].date if cells else None
    return SnapshotGridRow(
        investment_id=inv.id,
        name=inv.name,
        category=inv.category,
        base_currency=inv.base_currency,
        ticker=inv.ticker,
        cedear_ratio=cedear_ratios.get(inv.ticker) if inv.ticker else None,
        scope=SCOPE_PRIVATE if inv.pot_id is None else SCOPE_SHARED,
        pot_id=inv.pot_id,
        cadence=cadence,
        is_overdue=(False if cadence is None else is_valuation_overdue(cadence=cadence, valued_as_of=valued_as_of, holds_anything=True, today=today)),
        cells=cells,
    )


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
