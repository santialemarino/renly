# The snapshots grid, which PR 8b made scope-aware and weekly-capable (X2 + X4).
#
# Three things here were previously unreachable and are the reason this file exists: a co-owned holding
# appears at all, each row's freshness is measured against its OWN pot's cadence, and the columns are a
# server-side grid rather than month keys derived in the browser.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain.list_scope import SCOPE_PRIVATE, SCOPE_SHARED, ListScope
from app.domain.pot_monitoring import PotSeriesInterval
from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.pot import PotCadence
from app.models.snapshot import InvestmentSnapshot
from app.services import pot_service, snapshot_grid_service

TODAY = date(2026, 8, 26)


def _investment(investment_id: int, *, name: str = "Google", pot_id: int | None = None) -> Investment:
    return Investment(
        id=investment_id,
        user_id=None if pot_id is not None else 1,
        pot_id=pot_id,
        name=name,
        category=InvestmentCategory.stocks,
        base_currency=Currency.USD,
    )


def _snapshot(investment_id: int, day: date, value: str = "100") -> InvestmentSnapshot:
    return InvestmentSnapshot(
        id=investment_id * 1000 + day.toordinal() % 1000,
        investment_id=investment_id,
        user_id=1,
        date=day,
        value=Decimal(value),
        currency=Currency.USD,
        source="manual",
    )


def _scope(pot_id: int, *, cadence: PotCadence = PotCadence.monthly, can_write: bool = True) -> pot_service.PotScope:
    return pot_service.PotScope(pot_id=pot_id, name="Viaje", group_id=2, group_name="Casa", can_write=can_write, cadence=cadence)


# Wires the grid's four reads plus "today", which the freshness rule is measured against.
def _wire(monkeypatch, investments, snapshots, *, scopes=None):
    monkeypatch.setattr(snapshot_grid_service.metrics_repository, "list_active_investments", AsyncMock(return_value=investments))
    monkeypatch.setattr(snapshot_grid_service.metrics_repository, "list_snapshots_by_investments", AsyncMock(return_value=snapshots))
    monkeypatch.setattr(snapshot_grid_service.metrics_repository, "list_transactions_by_investments", AsyncMock(return_value=[]))
    monkeypatch.setattr(snapshot_grid_service.cedear_ratio_repository, "get_latest_by_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(snapshot_grid_service.pot_service, "list_visible_scopes", AsyncMock(return_value=scopes or []))
    # `date` is immutable, so the module's own alias is swapped for a subclass instead. A subclass
    # rather than a stub because the module uses date_type for the rate-map probe as well.
    monkeypatch.setattr(snapshot_grid_service, "date_type", type("_Date", (date,), {"today": classmethod(lambda cls: TODAY)}))


class TestColumns:
    @pytest.mark.asyncio
    async def test_monthly_columns_span_every_month_the_data_covers(self, monkeypatch):
        # Gaps included: a month nobody snapshotted still gets a column, because the grid's job is to
        # show that nothing was recorded there.
        _wire(monkeypatch, [_investment(7)], [_snapshot(7, date(2026, 5, 4)), _snapshot(7, date(2026, 8, 4))])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1)
        assert grid.columns == [date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31)]
        assert grid.interval == "monthly"

    @pytest.mark.asyncio
    async def test_weekly_columns_are_the_weeks_sundays(self, monkeypatch):
        _wire(monkeypatch, [_investment(7)], [_snapshot(7, date(2026, 8, 4)), _snapshot(7, date(2026, 8, 20))])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, interval=PotSeriesInterval.weekly)
        assert grid.columns == [date(2026, 8, 9), date(2026, 8, 16), date(2026, 8, 23)]
        assert grid.interval == "weekly"

    @pytest.mark.asyncio
    async def test_each_cell_names_the_column_it_belongs_to(self, monkeypatch):
        # The bucketing moved to the server so ONE rule decides which week a Wednesday is in. Two
        # snapshots in DIFFERENT weeks, so a constant column would show up as the same key twice.
        _wire(monkeypatch, [_investment(7)], [_snapshot(7, date(2026, 8, 19)), _snapshot(7, date(2026, 8, 24))])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, interval=PotSeriesInterval.weekly)
        assert [c.column for c in grid.rows[0].cells] == [date(2026, 8, 23), date(2026, 8, 30)]

    @pytest.mark.asyncio
    async def test_two_snapshots_in_one_column_both_survive_as_cells(self, monkeypatch):
        # The renderer picks the latest per column; the others stay so the form still knows which dates
        # are taken. Dropping them here would silently weaken the duplicate-date guard.
        _wire(monkeypatch, [_investment(7)], [_snapshot(7, date(2026, 8, 4)), _snapshot(7, date(2026, 8, 20))])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1)
        assert [c.date for c in grid.rows[0].cells] == [date(2026, 8, 4), date(2026, 8, 20)]
        assert {c.column for c in grid.rows[0].cells} == {date(2026, 8, 31)}

    @pytest.mark.asyncio
    async def test_weekly_columns_are_capped_where_monthly_ones_are_not(self, monkeypatch):
        # The cap is what makes weekly usable at all: this span is ~86 weeks, which as ~86 columns of
        # em-dashes is unreadable and, across twenty rows, thousands of cells. Monthly over the SAME
        # span is uncapped in practice, so one shared cap would silently truncate it too.
        span = [_snapshot(7, date(2025, 1, 6)), _snapshot(7, TODAY)]
        _wire(monkeypatch, [_investment(7)], span)
        weekly = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, interval=PotSeriesInterval.weekly)
        _wire(monkeypatch, [_investment(7)], span)
        monthly = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1)
        assert len(weekly.columns) == 52
        assert len(monthly.columns) == 20  # Jan 2025 through Aug 2026, uncapped
        # The cap keeps the MOST RECENT periods, so the newest snapshot still has a column to sit in.
        assert weekly.columns[-1] >= TODAY

    @pytest.mark.asyncio
    async def test_a_grid_with_no_rows_has_no_columns(self, monkeypatch):
        _wire(monkeypatch, [], [])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1)
        assert (grid.rows, grid.columns, grid.sections) == ([], [], [])


class TestScope:
    @pytest.mark.asyncio
    async def test_a_private_only_grid_resolves_no_pots(self, monkeypatch):
        # The DEFAULT, and it is what keeps the investor dashboard private: that page reads the same
        # repository function, and a co-owned holding's TWR is the pot's, not the viewer's.
        _wire(monkeypatch, [_investment(7)], [_snapshot(7, date(2026, 8, 4))])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1)
        snapshot_grid_service.pot_service.list_visible_scopes.assert_not_awaited()
        assert (grid.rows[0].scope, grid.rows[0].pot_id, grid.rows[0].cadence) == (SCOPE_PRIVATE, None, None)
        assert grid.sections == []

    @pytest.mark.asyncio
    async def test_a_co_owned_holding_appears_under_its_pots_section(self, monkeypatch):
        _wire(
            monkeypatch,
            [_investment(7), _investment(8, pot_id=4)],
            [_snapshot(7, date(2026, 8, 4)), _snapshot(8, date(2026, 8, 4))],
            scopes=[_scope(4)],
        )
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all)
        assert [(r.scope, r.pot_id) for r in grid.rows] == [(SCOPE_PRIVATE, None), (SCOPE_SHARED, 4)]
        assert [(s.scope, s.pot_id, s.group_name, s.can_write, s.count) for s in grid.sections] == [
            (SCOPE_PRIVATE, None, None, True, 1),
            (SCOPE_SHARED, 4, "Casa", True, 1),
        ]

    @pytest.mark.asyncio
    async def test_a_section_reports_whether_the_caller_may_snapshot_it(self, monkeypatch):
        # Snapshotting a shared holding needs pot WRITE access, so the grid has to say so before
        # offering the action — a Radix tooltip never fires on a disabled trigger, so the alternative
        # is an action that silently does nothing.
        _wire(monkeypatch, [_investment(8, pot_id=4)], [_snapshot(8, date(2026, 8, 4))], scopes=[_scope(4, can_write=False)])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all)
        assert grid.sections[0].can_write is False

    @pytest.mark.asyncio
    async def test_sorting_by_name_orders_within_each_scope(self, monkeypatch):
        # `reverse=True` over a composite key would reverse the SCOPE order too and put the caller's
        # own holdings last, which is why the sort is two stable passes.
        _wire(
            monkeypatch,
            [_investment(7, name="Zeta"), _investment(9, name="Alpha"), _investment(8, name="Mid", pot_id=4)],
            [_snapshot(7, date(2026, 8, 4)), _snapshot(8, date(2026, 8, 4)), _snapshot(9, date(2026, 8, 4))],
            scopes=[_scope(4)],
        )
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all, sort_by="name", sort_order="desc")
        assert [(r.name, r.pot_id) for r in grid.rows] == [("Zeta", None), ("Alpha", None), ("Mid", 4)]


class TestFreshness:
    @pytest.mark.asyncio
    async def test_a_shared_row_carries_its_pots_cadence(self, monkeypatch):
        _wire(monkeypatch, [_investment(8, pot_id=4)], [_snapshot(8, TODAY)], scopes=[_scope(4, cadence=PotCadence.weekly)])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all)
        assert (grid.rows[0].cadence, grid.rows[0].is_overdue) == (PotCadence.weekly, False)

    @pytest.mark.asyncio
    async def test_a_holding_behind_its_cadence_is_flagged(self, monkeypatch):
        # Nine days on a weekly pot is late; the same nine days on a monthly one is not — so the flag
        # is genuinely read from the pot's own cadence rather than from a fixed window.
        stale = TODAY.replace(day=17)
        for cadence, expected in ((PotCadence.weekly, True), (PotCadence.monthly, False), (PotCadence.ad_hoc, False)):
            _wire(monkeypatch, [_investment(8, pot_id=4)], [_snapshot(8, stale)], scopes=[_scope(4, cadence=cadence)])
            grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all)
            assert grid.rows[0].is_overdue is expected, cadence

    @pytest.mark.asyncio
    async def test_freshness_reads_the_LATEST_snapshot_and_not_the_first(self, monkeypatch):
        # TWO snapshots, one ancient and one current. With a single-snapshot fixture `[0]` and `[-1]`
        # are the same row, so reading the wrong end of the history is invisible — a mutation sweep
        # proved exactly that, and a holding valued yesterday would have read as years overdue.
        _wire(
            monkeypatch,
            [_investment(8, pot_id=4)],
            [_snapshot(8, date(2024, 1, 1)), _snapshot(8, TODAY)],
            scopes=[_scope(4, cadence=PotCadence.weekly)],
        )
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all)
        assert grid.rows[0].is_overdue is False

    @pytest.mark.asyncio
    async def test_freshness_reads_the_holdings_own_latest_snapshot(self, monkeypatch):
        # Two shared holdings in ONE pot, one current and one stale: a flag read from the pot rather
        # than from the row would mark both the same way.
        _wire(
            monkeypatch,
            [_investment(8, name="Fresh", pot_id=4), _investment(9, name="Stale", pot_id=4)],
            [_snapshot(8, TODAY), _snapshot(9, date(2026, 6, 1))],
            scopes=[_scope(4, cadence=PotCadence.weekly)],
        )
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1, scope=ListScope.all)
        assert [(r.name, r.is_overdue) for r in grid.rows] == [("Fresh", False), ("Stale", True)]

    @pytest.mark.asyncio
    async def test_a_private_row_is_never_overdue(self, monkeypatch):
        # It declares no rhythm, so there is nothing to be late against.
        _wire(monkeypatch, [_investment(7)], [_snapshot(7, date(2020, 1, 1))])
        grid = await snapshot_grid_service.get_snapshot_grid(AsyncMock(), 1)
        assert (grid.rows[0].cadence, grid.rows[0].is_overdue) == (None, False)
