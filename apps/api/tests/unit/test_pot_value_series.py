# The pot's value series: what it plots, where it starts, and the one property that keeps it honest.
#
# The series is a SECOND way to compute a figure get_valuation already computes, at a dozen dates
# instead of one, from batched reads instead of per-date ones. Two ways to compute one number is the
# shape that goes wrong quietly, so the load-bearing test is the parity one below: every point must
# equal what the point-in-time engine says for that same date, and both are driven from ONE fixture of
# snapshots and balances so the only way they can disagree is if the code does.
#
# The rest are about honesty rather than arithmetic. A point is null in exactly the cases the NAV is
# null — which on a real pot is most of the early points — and `my_value` is null while nobody holds
# any units, because before the baseline there is no ownership to state and a zero would assert
# something the ledger has not said.

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain.pot_monitoring import PotSeriesInterval, period_ends
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.investment import Investment, InvestmentCategory
from app.models.pot import OwnershipEventType, Pot, PotCadence, PotMemberPermission, PotOwnershipEvent, PotVisibility
from app.models.snapshot import InvestmentSnapshot
from app.models.user import User
from app.services import pot_service

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
OTHER_SEAT = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member)

# Far enough back that every point of a 4-month series sits after it, so a test that is not about the
# anchor never trips over it.
CREATED = date(2020, 1, 1)


# The dates the service will actually produce, derived from the same pure function it uses. Fixture
# snapshots are placed RELATIVE to these rather than at literal dates: a literal makes the expected
# figures depend on what month the suite happens to run in, which is a test that passes today and
# fails in October for no reason anyone will connect to this file.
def _grid(count: int, interval: PotSeriesInterval = PotSeriesInterval.monthly) -> list[date]:
    return period_ends(date.today(), interval, count)


def _pot(**kwargs) -> Pot:
    defaults = dict(
        id=5,
        group_id=10,
        name=None,
        base_currency="USD",
        snapshot_cadence=PotCadence.monthly,
        visibility=PotVisibility.members,
        is_default=True,
    )
    pot = Pot(**{**defaults, **kwargs})
    pot.created_at = kwargs.pop("created_at", None) or _midnight(CREATED)
    return pot


def _midnight(d: date):
    from datetime import datetime

    return datetime(d.year, d.month, d.day)


def _snapshot(investment_id: int, on: date, value: str, *, currency: str = "USD") -> InvestmentSnapshot:
    return InvestmentSnapshot(id=None, investment_id=investment_id, user_id=None, pot_id=5, date=on, value=Decimal(value), currency=currency)


# The pot's holdings are read as whole rows now (the valuation labels each one with its composition
# bucket), so the fixtures name a category. It is the same category throughout: nothing in this file is
# about the bucket, only about which figure lands at which point.
def _investment(investment_id: int) -> Investment:
    return Investment(id=investment_id, user_id=None, pot_id=5, name=f"I{investment_id}", category=InvestmentCategory.fci, base_currency="USD")


def _account(account_id: int, *, currency: str = "USD", opening: date = CREATED) -> Account:
    return Account(id=account_id, user_id=None, pot_id=5, name=f"A{account_id}", type=AccountType.bank, currency=currency, opening_date=opening)


def _opening(member_id: int, on: date, units: str) -> PotOwnershipEvent:
    return PotOwnershipEvent(
        id=None,
        pot_id=5,
        type=OwnershipEventType.opening,
        date=on,
        member_id=member_id,
        units=Decimal(units),
        unit_price=Decimal(1),
    )


# Stubs everything get_value_series reaches except the visibility gate. `snapshots` is the whole
# window's rows (what the batched read returns) and `balances` is {account_id: [one figure per point]}.
def _wire(monkeypatch, *, pot=None, investments=(), accounts=(), snapshots=(), balances=None, events=(), rates=None, rate_map_for=None):
    pot = pot or _pot()
    monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=pot))
    monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
    monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=PotMemberPermission(pot_id=5, member_id=100)))
    monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=list(events)))
    rows = [_investment(investment_id) for investment_id in investments]
    monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=rows))
    monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=list(accounts)))
    listed = AsyncMock(return_value=list(snapshots))
    monkeypatch.setattr(pot_service.snapshot_repository, "list_by_investments", listed)
    series = AsyncMock(return_value=dict(balances or {}))
    monkeypatch.setattr(pot_service.account_service, "compute_account_balance_series", series)
    lookup = AsyncMock()
    # `rate_map_for` is the per-DATE variant, for the one property a single flat map cannot express.
    lookup.get_rate_map_at = rate_map_for or (lambda _d: {"USD": Decimal(1)} if rates is None else rates)
    monkeypatch.setattr(pot_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))
    return (listed, series)


class TestAgreementWithThePointInTimeValuation:
    @pytest.mark.asyncio
    async def test_every_point_equals_what_get_valuation_says_for_that_date(self, monkeypatch):
        # THE test. Both engines are driven from the SAME snapshots and the SAME balances, so a series
        # that picked the wrong snapshot for a date, mis-indexed a balance, or applied the null rule
        # differently reddens here at the point it happens.
        #
        # The fixture is chosen so the answer differs at every point: an investment snapshotted twice
        # inside the window, a second one whose first snapshot arrives mid-window (so the earlier
        # points are legitimately unknown), and an account whose balance moves.
        grid = _grid(4)
        rows = [
            _snapshot(1, grid[0], "100.00"),
            _snapshot(1, grid[1] + timedelta(days=1), "130.00"),
            _snapshot(2, grid[1] + timedelta(days=1), "40.00"),
        ]
        balances = {9: [Decimal("10.00"), Decimal("10.00"), Decimal("25.00"), Decimal("25.00")]}
        _wire(monkeypatch, investments=[1, 2], accounts=[_account(9)], snapshots=rows, balances=balances)

        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)
        dates = [point.date for point in series.points]

        # The point-in-time engine, stubbed from the same rows: the latest snapshot per investment on
        # or before the date, and that date's balance.
        def latest_at(as_of_date):
            return {row.investment_id: row for row in sorted((r for r in rows if r.date <= as_of_date), key=lambda r: r.date)}

        for index, point_date in enumerate(dates):
            monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value=latest_at(point_date)))
            monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value={9: balances[9][index]}))
            lookup = AsyncMock()
            lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
            expected = await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=point_date, lookup=lookup)
            assert series.points[index].nav == expected, point_date

    @pytest.mark.asyncio
    async def test_MY_SHARE_at_every_point_equals_what_get_member_share_says(self, monkeypatch):
        # The same parity, one level up, and the one the dashboard now rests on: the chart's Shared
        # line reads compute_share_series while the headline's Shared figure reads get_member_share, so
        # a reader compares the two at a glance. Both engines are driven from the same snapshots,
        # balances and ledger here, and the ledger moves inside the window so the share is not constant.
        grid = _grid(4)
        rows = [_snapshot(1, grid[0], "100.00"), _snapshot(1, grid[2], "300.00")]
        balances = {9: [Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")]}
        events = [_opening(SEAT.id, grid[0], "60"), _opening(OTHER_SEAT.id, grid[0], "40")]
        _wire(monkeypatch, investments=[1], accounts=[_account(9)], snapshots=rows, balances=balances, events=events)

        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)

        def latest_at(as_of_date):
            return {row.investment_id: row for row in sorted((r for r in rows if r.date <= as_of_date), key=lambda r: r.date)}

        seat = pot_service.PotSeat(pot=_pot(), member_id=SEAT.id, events=events)
        for index, point in enumerate(series.points):
            monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value=latest_at(point.date)))
            monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value={9: balances[9][index]}))
            lookup = AsyncMock()
            lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
            expected = await pot_service.get_member_share(AsyncMock(), seat, as_of_date=point.date, lookup=lookup)
            assert point.my_value == expected.value, point.date

        # The positive control: 60% of 100 then of 300, so neither engine can be answering None or a
        # constant and still agree.
        assert [point.my_value for point in series.points] == [Decimal("60.00"), Decimal("60.00"), Decimal("180.00"), Decimal("180.00")]

    @pytest.mark.asyncio
    async def test_the_series_is_not_flat(self, monkeypatch):
        # The positive control for the parity test: a series that answered None everywhere, or repeated
        # one figure, would satisfy an equality check against an engine stubbed the same wrong way.
        grid = _grid(4)
        rows = [
            _snapshot(1, grid[0], "100.00"),
            _snapshot(1, grid[1] + timedelta(days=1), "130.00"),
            _snapshot(2, grid[1] + timedelta(days=1), "40.00"),
        ]
        balances = {9: [Decimal("10.00"), Decimal("10.00"), Decimal("25.00"), Decimal("25.00")]}
        _wire(monkeypatch, investments=[1, 2], accounts=[_account(9)], snapshots=rows, balances=balances)
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)
        # The first two points: investment 2 has no snapshot yet, so the whole figure is unknown. From
        # the third on, both are valued: 130 + 40, plus that point's own account balance.
        assert [point.nav for point in series.points] == [None, None, Decimal("195.00"), Decimal("195.00")]


class TestWhatAPointMeans:
    @pytest.mark.asyncio
    async def test_a_point_before_a_holdings_first_snapshot_is_unknown_and_not_zero(self, monkeypatch):
        # The single most common shape a real pot produces, and the one the refusal rule exists for: a
        # holding moved in last month has no valuation for the months before it, so those points are
        # genuinely unknown. A zero there would draw a line up from nothing and read as growth.
        grid = _grid(4)
        _wire(monkeypatch, investments=[1], snapshots=[_snapshot(1, grid[2], "500.00")])
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)
        assert [point.nav for point in series.points] == [None, None, Decimal("500.00"), Decimal("500.00")]

    @pytest.mark.asyncio
    async def test_a_snapshot_after_the_last_point_is_not_asked_for(self, monkeypatch):
        # Asserted on the argument the service PASSED. A future-dated snapshot is not a valuation of
        # today, and letting one in would make the last point disagree with the pot header.
        listed, _ = _wire(monkeypatch, investments=[1], snapshots=[])
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert listed.await_args.kwargs == {"until": series.points[-1].date}
        assert series.points[-1].date == date.today()

    @pytest.mark.asyncio
    async def test_an_unconvertible_holding_makes_that_point_unknown_rather_than_partial(self, monkeypatch):
        _wire(
            monkeypatch,
            investments=[1],
            accounts=[_account(9)],
            snapshots=[_snapshot(1, date(2026, 1, 5), "100.00", currency="BRL")],
            balances={9: [Decimal("10.00")] * 4},
            rates={},
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)
        assert all(point.nav is None for point in series.points)

    @pytest.mark.asyncio
    async def test_a_pot_holding_nothing_reports_a_grid_of_unknowns(self, monkeypatch):
        # The section still renders — with nothing on it. A zero line would say the pot is worth
        # nothing, which is a claim, where "we have nothing to value" is the fact.
        _wire(monkeypatch)
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)
        assert len(series.points) == 4
        assert all(point.nav is None and point.my_value is None for point in series.points)


class TestEachPointIsItsOwn:
    # Three properties a series can get wrong while every figure still looks plausible, because each
    # one only shows up when the input actually VARIES across the window. A mutation sweep found all
    # three: with a flat fixture, reading the last balance at every point, converting everything at
    # today's rate, and counting an event a day late are all indistinguishable from the real thing.

    @pytest.mark.asyncio
    async def test_each_point_uses_ITS_OWN_account_balance(self, monkeypatch):
        # Not the latest one. A pot whose cash balance moved mid-window would otherwise report today's
        # balance at every historical point, quietly restating the past as the present.
        _wire(
            monkeypatch,
            accounts=[_account(9)],
            balances={9: [Decimal("10.00"), Decimal("20.00"), Decimal("30.00")]},
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert [point.nav for point in series.points] == [Decimal("10.00"), Decimal("20.00"), Decimal("30.00")]

    @pytest.mark.asyncio
    async def test_each_point_converts_at_ITS_OWN_date(self, monkeypatch):
        # The rule the evolution chart already follows and currency-handling.md now records for this
        # one: a historical point converted at today's rate changes every time the rate moves, so
        # re-opening the page tomorrow would show a different past.
        grid = _grid(3)
        # A rate that MOVES across the window. `rates` is keyed by date and indexed directly, so a
        # series asking for any date other than the point's own raises rather than quietly passing.
        rates = {grid[0]: Decimal(4), grid[1]: Decimal(2), grid[2]: Decimal(1)}
        _wire(
            monkeypatch,
            investments=[1],
            snapshots=[_snapshot(1, date(2020, 2, 1), "100.00", currency="ARS")],
            rate_map_for=lambda d: {"USD": Decimal(1), "ARS": rates[d]},
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        # 100 ARS at 4, 2 and 1 ARS-per-USD is 25, 50 and 100 USD — three different answers from one
        # unchanged snapshot, which is the whole point.
        assert [point.nav for point in series.points] == [Decimal("25.00"), Decimal("50.00"), Decimal("100.00")]

    @pytest.mark.asyncio
    async def test_an_event_dated_ON_a_point_counts_at_that_point(self, monkeypatch):
        # The walk is `<=`, not `<`. An opening recorded on a month-end is agreed AS OF that date, so
        # a strict comparison would show the pot undivided for one whole period after it was divided.
        grid = _grid(3)
        _wire(
            monkeypatch,
            investments=[1],
            snapshots=[_snapshot(1, date(2020, 2, 1), "1000.00")],
            events=[_opening(SEAT.id, grid[1], "100")],
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert series.points[0].my_value is None
        assert series.points[1].my_value == Decimal("1000.00")


class TestYourShare:
    @pytest.mark.asyncio
    async def test_your_share_is_unknown_before_the_baseline_rather_than_zero(self, monkeypatch):
        # With no units outstanding nobody owns any share of anything, which is what
        # ownership_percentages already says about an undivided pot. A zero would be the ledger
        # asserting something it has not been told.
        _wire(
            monkeypatch,
            investments=[1],
            snapshots=[_snapshot(1, date(2020, 2, 1), "100.00")],
            events=[_opening(SEAT.id, date.today(), "60")],
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert [point.my_value for point in series.points[:-1]] == [None, None]

    @pytest.mark.asyncio
    async def test_your_share_follows_the_ledger_as_at_each_point(self, monkeypatch):
        # A pot divided 60/40 partway through the window: before the opening there is no share to
        # state, and from it onwards the viewer's own 60% of the pot's value at that date.
        opened = date.today().replace(day=1)
        _wire(
            monkeypatch,
            investments=[1],
            snapshots=[_snapshot(1, date(2020, 2, 1), "1000.00")],
            events=[_opening(SEAT.id, opened, "60"), _opening(OTHER_SEAT.id, opened, "40")],
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert series.points[-1].my_value == Decimal("600.00")
        assert series.points[0].my_value is None

    @pytest.mark.asyncio
    async def test_a_share_worth_nothing_yet_is_unknown_when_the_pot_is(self, monkeypatch):
        # If the pot's value cannot be stated, neither can anyone's slice of it — a share value with no
        # NAV behind it would be arithmetic on a number that does not exist.
        _wire(monkeypatch, investments=[1], snapshots=[], events=[_opening(SEAT.id, date(2020, 2, 1), "100")])
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert all(point.my_value is None for point in series.points)


class TestTheGrid:
    @pytest.mark.asyncio
    async def test_the_grid_follows_the_pots_cadence(self, monkeypatch):
        _wire(monkeypatch, pot=_pot(snapshot_cadence=PotCadence.weekly))
        weekly = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert weekly.interval == PotSeriesInterval.weekly

    @pytest.mark.asyncio
    async def test_an_ad_hoc_pot_says_monthly_rather_than_echoing_its_cadence(self, monkeypatch):
        # The response describes ITS OWN points. Echoing 'ad_hoc' here would name a grid that does not
        # exist and leave the caller to re-derive the mapping.
        _wire(monkeypatch, pot=_pot(snapshot_cadence=PotCadence.ad_hoc))
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=3)
        assert series.interval == PotSeriesInterval.monthly

    @pytest.mark.asyncio
    async def test_the_series_never_starts_before_the_pot_existed(self, monkeypatch):
        # A shared investment brings its whole snapshot history with it, so without this bound a pot
        # created last week would report years of "the pot's value" for a pot that did not exist.
        created = _midnight(date.today().replace(day=1))
        _wire(monkeypatch, pot=_pot(created_at=created), investments=[1], snapshots=[_snapshot(1, date(2015, 1, 1), "9.00")])
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=12)
        assert all(point.date >= created.date() for point in series.points)
        assert series.points[-1].date == date.today()

    @pytest.mark.asyncio
    async def test_a_back_dated_opening_moves_the_start_EARLIER_than_creation(self, monkeypatch):
        # The co-owners can agree their division began before they recorded it, and §5.4 allows exactly
        # that. The anchor is the earliest of the two, not the pot row's own timestamp.
        created = _midnight(date.today().replace(day=1))
        opened = _grid(6)[0]
        _wire(
            monkeypatch,
            pot=_pot(created_at=created),
            investments=[1],
            snapshots=[_snapshot(1, date(2015, 1, 1), "9.00")],
            events=[_opening(SEAT.id, opened, "100")],
        )
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=12)
        assert series.points[0].date >= opened
        assert len(series.points) > 1

    @pytest.mark.asyncio
    async def test_a_pot_created_today_still_gets_its_one_point(self, monkeypatch):
        # The anchor must never leave the grid empty; the section would have nothing to render and the
        # page would look broken on the very first visit.
        _wire(monkeypatch, pot=_pot(created_at=_midnight(date.today())))
        series = await pot_service.get_value_series(AsyncMock(), 5, USER, periods=12)
        assert [point.date for point in series.points] == [date.today()]


class TestCost:
    @pytest.mark.asyncio
    async def test_the_whole_series_costs_ONE_snapshot_read_and_ONE_balance_read(self, monkeypatch):
        # The reason this function exists rather than a loop over get_valuation, which is ten queries
        # per point. Asserted on the await counts, because that is the property — not the numbers.
        listed, series_call = _wire(
            monkeypatch,
            investments=[1, 2, 3],
            accounts=[_account(9), _account(8)],
            snapshots=[_snapshot(i, date(2020, 2, 1), "10.00") for i in (1, 2, 3)],
            balances={9: [Decimal("1.00")] * 12, 8: [Decimal("2.00")] * 12},
        )
        await pot_service.get_value_series(AsyncMock(), 5, USER, periods=12)
        assert (listed.await_count, series_call.await_count) == (1, 1)
        assert listed.await_args.args[1] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_a_pot_the_caller_may_not_see_answers_404_rather_than_an_empty_series(self, monkeypatch):
        _wire(monkeypatch)
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot(visibility=PotVisibility.owners)))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=None))
        from app.domain import NotFoundError

        with pytest.raises(NotFoundError):
            await pot_service.get_value_series(AsyncMock(), 5, USER, periods=4)
