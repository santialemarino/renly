# The batched balance series, and the one property that makes it safe to exist.
#
# compute_account_balance_series is a SECOND way to compute a figure compute_account_balances_at
# already computes. Two ways to compute one number is exactly the shape that goes wrong quietly, so
# the load-bearing test here is not "does it add up" but "does it agree with the other one, at every
# date, over every term of the union". Both are driven from ONE movement fixture below, which is what
# makes the comparison mean anything: derive the two stub shapes from the same rows and the only way
# they can disagree is if the code does.
#
# The union has TEN terms and three of them can only ever be empty for a pot's accounts (a shared
# account cannot carry private entries at all). They are fixtured anyway. Dropping a term because a
# guard currently makes it empty is how a sum ends up agreeing with reality only for as long as that
# guard holds — the shape §18 recorded.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.account import Account, AccountType
from app.services import account_service

# (account_id, date, amount) per source. Deliberately includes: two sources on the SAME day for one
# account (so a merge that overwrites instead of adding is caught), a movement between two points, a
# movement before the first point, and one on a point's own date (the bound is inclusive).
_MOVEMENTS: dict[str, list[tuple[int, date, Decimal]]] = {
    "income": [(1, date(2026, 3, 10), Decimal("500.00")), (1, date(2026, 5, 31), Decimal("40.00"))],
    "expenses": [(1, date(2026, 4, 2), Decimal("120.00")), (2, date(2026, 6, 15), Decimal("9.00"))],
    "settlements": [(1, date(2026, 3, 10), Decimal("30.00"))],
    "transfers_in": [(2, date(2026, 4, 20), Decimal("250.00"))],
    "transfers_out": [(1, date(2026, 6, 1), Decimal("75.00"))],
    "ownership_in": [(1, date(2026, 5, 5), Decimal("1000.00")), (2, date(2026, 7, 4), Decimal("60.00"))],
    "ownership_out": [(2, date(2026, 4, 20), Decimal("10.00"))],
    # The flow half. A shared expense drawn from account 1, and both legs of a group settlement — one
    # on each account, so a sign flipped on either is visible rather than cancelling out.
    "shared_expenses": [(1, date(2026, 6, 10), Decimal("300.00"))],
    "group_settlements_in": [(1, date(2026, 7, 8), Decimal("180.00"))],
    "group_settlements_out": [(2, date(2026, 5, 2), Decimal("25.00"))],
}

_DATES = [date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31)]


def _account(account_id: int, *, opening_balance: str = "0", opening_date: date = date(2026, 1, 1)) -> Account:
    return Account(
        id=account_id,
        user_id=None,
        pot_id=5,
        name=f"Account {account_id}",
        type=AccountType.bank,
        currency="USD",
        opening_balance=Decimal(opening_balance),
        opening_date=opening_date,
    )


# The dated shape the series reads: every row for the accounts asked about, bounded above by `until`.
# Both filters mirror the real query (`leg.in_(account_ids)` and `date <= until`) — a stub that
# returned rows for an account nobody asked about would be testing a shape the database cannot produce.
def _dated(source: str, account_ids: list[int], until: date) -> list[tuple[int, date, Decimal]]:
    return [row for row in _MOVEMENTS[source] if row[0] in account_ids and row[1] <= until]


# The point-in-time shape the existing engine reads: the same rows summed per account up to a date.
def _at(source: str, account_ids: list[int], as_of_date: date) -> dict[int, Decimal]:
    totals: dict[int, Decimal] = {}
    for account_id, movement_date, amount in _MOVEMENTS[source]:
        if account_id in account_ids and movement_date <= as_of_date:
            totals[account_id] = totals.get(account_id, Decimal(0)) + amount
    return totals


# Stubs the seven dated sums the series reads. The `until` each one is handed is honoured by the
# fixture rather than ignored, so a series that failed to bound its window would come back wrong.
def _stub_dated(monkeypatch) -> None:
    for repo, method, source in (
        (account_service.income_repository, "sum_by_account_ids_dated", "income"),
        (account_service.expense_repository, "sum_by_account_ids_dated", "expenses"),
        (account_service.card_settlement_repository, "sum_by_account_ids_dated", "settlements"),
        (account_service.transfer_repository, "sum_in_by_account_ids_dated", "transfers_in"),
        (account_service.transfer_repository, "sum_out_by_account_ids_dated", "transfers_out"),
        (account_service.pot_ownership_repository, "sum_in_by_account_ids_dated", "ownership_in"),
        (account_service.pot_ownership_repository, "sum_out_by_account_ids_dated", "ownership_out"),
        (account_service.shared_expense_repository, "sum_by_account_ids_dated", "shared_expenses"),
        (account_service.group_settlement_repository, "sum_in_by_account_ids_dated", "group_settlements_in"),
        (account_service.group_settlement_repository, "sum_out_by_account_ids_dated", "group_settlements_out"),
    ):

        def handler(_session, account_ids, *_args, until: date, _source=source, **_kwargs):
            return _dated(_source, account_ids, until)

        monkeypatch.setattr(repo, method, AsyncMock(side_effect=handler))


# Stubs the seven point-in-time sums the existing engine reads, from the same fixture.
def _stub_at(monkeypatch) -> None:
    for repo, method, source in (
        (account_service.income_repository, "sum_by_account_ids", "income"),
        (account_service.expense_repository, "sum_by_account_ids", "expenses"),
        (account_service.card_settlement_repository, "sum_by_account_ids", "settlements"),
        (account_service.transfer_repository, "sum_in_by_account_ids", "transfers_in"),
        (account_service.transfer_repository, "sum_out_by_account_ids", "transfers_out"),
        (account_service.pot_ownership_repository, "sum_in_by_account_ids", "ownership_in"),
        (account_service.pot_ownership_repository, "sum_out_by_account_ids", "ownership_out"),
        (account_service.shared_expense_repository, "sum_by_account_ids", "shared_expenses"),
        (account_service.group_settlement_repository, "sum_in_by_account_ids", "group_settlements_in"),
        (account_service.group_settlement_repository, "sum_out_by_account_ids", "group_settlements_out"),
    ):

        def handler(_session, account_ids, *_args, as_of_date: date, _source=source, **_kwargs):
            return _at(_source, account_ids, as_of_date)

        monkeypatch.setattr(repo, method, AsyncMock(side_effect=handler))


class TestAgreementWithThePointInTimeEngine:
    @pytest.mark.asyncio
    async def test_every_point_equals_what_the_point_in_time_balance_says_for_that_date(self, monkeypatch):
        # THE test. A series is only worth having if it is the same figure the pot page shows, and the
        # only way to know that is to compute both and compare — one term dropped, one sign flipped or
        # one date bound missed and this reddens at the point it happens.
        accounts = [_account(1, opening_balance="200.00"), _account(2, opening_balance="50.00")]
        _stub_dated(monkeypatch)
        _stub_at(monkeypatch)
        series = await account_service.compute_account_balance_series(AsyncMock(), accounts, dates=_DATES)
        for index, point_date in enumerate(_DATES):
            expected = await account_service.compute_account_balances_at(AsyncMock(), accounts, as_of_date=point_date)
            assert {account_id: points[index] for account_id, points in series.items()} == expected, point_date

    @pytest.mark.asyncio
    async def test_the_figures_are_not_all_identical(self, monkeypatch):
        # The positive control for the test above: returning the same balance at every point would
        # satisfy an equality check against an engine stubbed the same wrong way, so assert the series
        # actually moves.
        accounts = [_account(1, opening_balance="200.00")]
        _stub_dated(monkeypatch)
        series = await account_service.compute_account_balance_series(AsyncMock(), accounts, dates=_DATES)
        assert series[1] == [
            Decimal("670.00"),  # 200 opening + 500 income - 30 card settlement, both dated 10 March
            Decimal("550.00"),  # - 120 expense on 2 April
            Decimal("1590.00"),  # + 1000 ownership in on 5 May, + 40 income on the 31st itself
            Decimal("1215.00"),  # - 75 transferred out on 1 June, - 300 shared expense on the 10th
            Decimal("1395.00"),  # + 180 group settlement received on 8 July
        ]


class TestBounds:
    @pytest.mark.asyncio
    async def test_the_window_is_bounded_by_the_LAST_point_and_nothing_further(self, monkeypatch):
        # Asserted on the argument the service passed, not on what the stub handed back: a stub
        # returns whatever it was told either way, so only the `until` proves the bound exists.
        _stub_dated(monkeypatch)
        dated = AsyncMock(return_value=[])
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids_dated", dated)
        await account_service.compute_account_balance_series(AsyncMock(), [_account(1)], dates=_DATES)
        assert dated.await_args.kwargs == {"until": _DATES[-1]}

    @pytest.mark.asyncio
    async def test_the_opening_balance_only_counts_from_its_own_date(self, monkeypatch):
        # Before the account existed its balance is zero, not its eventual opening figure — the same
        # bound the point-in-time version applies, and the one that stops a pot's history claiming
        # money that had not arrived.
        _stub_dated(monkeypatch)
        account = _account(3, opening_balance="900.00", opening_date=date(2026, 5, 15))
        series = await account_service.compute_account_balance_series(AsyncMock(), [account], dates=_DATES)
        assert series[3] == [Decimal(0), Decimal(0), Decimal("900.00"), Decimal("900.00"), Decimal("900.00")]

    @pytest.mark.asyncio
    async def test_no_accounts_and_no_dates_each_short_circuit_to_nothing(self, monkeypatch):
        income = AsyncMock(return_value=[])
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids_dated", income)
        assert await account_service.compute_account_balance_series(AsyncMock(), [], dates=_DATES) == {}
        assert await account_service.compute_account_balance_series(AsyncMock(), [_account(1)], dates=[]) == {}
        income.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_account_with_no_movements_at_all_still_gets_a_point_per_date(self, monkeypatch):
        # The chart needs one value per point; a missing key would be an undrawable gap that means
        # "no movements" rather than "unknown".
        _stub_dated(monkeypatch)
        series = await account_service.compute_account_balance_series(AsyncMock(), [_account(4, opening_balance="7.00")], dates=_DATES)
        assert series[4] == [Decimal("7.00")] * len(_DATES)
