# The shared half of a net worth: what it counts, what it refuses to count, and what it names.
#
# The rule every test here defends is X1's: your share of a co-owned asset is yours, and VISIBILITY
# NEVER INFLATES NET WORTH. Two states make that concrete and both are reachable — a pot you may see
# but own none of, and a pot whose owners have not agreed a division yet — so both are asserted to
# contribute exactly zero rather than left to the reader of the code.
#
# The second subject is the receivable/payable split. D3 makes an owed balance its own net-worth line,
# which means the two directions must not be netted before they are reported: somebody owed 100 in one
# group and owing 100 in another is not somebody with no balances.

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.group import GroupMember, GroupMemberRole
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent, PotVisibility
from app.schemas.pot import PotValueSeriesPoint
from app.services import pot_service, shared_worth_service

TODAY = date(2026, 7, 15)
RATE_MAP = {"USD": Decimal("1"), "ARS": Decimal("1000")}


class _FixedLookup:
    def __init__(self, rate_map: dict[str, Decimal] | None = None) -> None:
        self._rate_map = RATE_MAP if rate_map is None else rate_map

    def get_rate_map_at(self, _as_of_date: date) -> dict[str, Decimal] | None:
        return self._rate_map


def _seat(member_id: int, group_id: int = 10) -> GroupMember:
    return GroupMember(id=member_id, group_id=group_id, user_id=1, display_name="Santi", role=GroupMemberRole.member)


def _pot(pot_id: int = 5, *, group_id: int = 10, name: str | None = None, currency: str = "USD") -> Pot:
    pot = Pot(id=pot_id, group_id=group_id, name=name, base_currency=currency, visibility=PotVisibility.members, is_default=True)
    pot.created_at = datetime(2026, 1, 1)
    return pot


def _pot_seat(pot: Pot | None = None, *, member_id: int = 100, events: list | None = None) -> pot_service.PotSeat:
    return pot_service.PotSeat(pot=pot or _pot(), member_id=member_id, events=events or [])


def _event(on: date, member_id: int = 100) -> PotOwnershipEvent:
    return PotOwnershipEvent(
        id=1, pot_id=5, type=OwnershipEventType.opening, date=on, member_id=member_id, units=Decimal("100"), unit_price=Decimal("1")
    )


def _context(*, seats=(), pots=(), positions=()) -> shared_worth_service.SharedContext:
    return shared_worth_service.SharedContext(seats=list(seats), pots=list(pots), positions=list(positions))


# The context's positions as the dashboard reads them: the cumulative position at the end of every
# month that moved. The headline takes the LAST entry, which is today's position by construction.
def _standing(by_group, month=(2026, 7)):
    return [(month, by_group)]


# Stubs the one pot read get_shared_worth makes, with the same answer for every pot it is asked about.
def _share(monkeypatch, *, nav, value, weights=None, holds_anything=True) -> None:
    monkeypatch.setattr(
        pot_service,
        "get_member_share",
        AsyncMock(return_value=pot_service.PotShare(nav=nav, value=value, weights=weights or {}, holds_anything=holds_anything)),
    )


async def _worth(monkeypatch, context, *, currency: str | None = "USD", lookup=None) -> shared_worth_service.SharedWorth:
    return await shared_worth_service.get_shared_worth(
        AsyncMock(),
        1,
        context,
        currency=currency,
        lookup=lookup if lookup is not None else _FixedLookup(),
        as_of_date=TODAY,
    )


class TestVisibilityNeverInflates:
    @pytest.mark.asyncio
    async def test_a_pot_you_own_none_of_contributes_zero_and_is_not_flagged(self, monkeypatch):
        # V3: a member may hold 0% and still see the pot — an adult child watching the family
        # portfolio. share_values gives them no row, so their share is zero, and there is nothing
        # half-finished about it: the pot IS divided, just not to them.
        _share(monkeypatch, nav=Decimal("100000"), value=Decimal("0"), weights={"fci": Decimal("100000")})
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)]))
        assert worth.pot_value == Decimal("0")
        assert worth.total == Decimal("0")
        assert worth.undivided_pots == []

    @pytest.mark.asyncio
    async def test_an_undivided_pot_holding_value_contributes_zero_and_IS_named(self, monkeypatch):
        # The reachable surprise: moving your own holding into a fresh pot before recording the
        # opening drops it out of your net worth, because nobody owns any share of anything yet.
        # Nothing may be attributed — so the pot is named instead, and the breakdown says why.
        _share(monkeypatch, nav=Decimal("100000"), value=None, holds_anything=True)
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)]))
        assert worth.pot_value == Decimal("0")
        assert [(p.pot_id, p.name, p.group_id) for p in worth.undivided_pots] == [(5, None, 10)]

    @pytest.mark.asyncio
    async def test_an_EMPTY_pot_is_silent(self, monkeypatch):
        # A container with nothing in it is not a half-finished setup: there is no missing value to
        # explain, so naming it would put a permanent unexplained line on the dashboard.
        _share(monkeypatch, nav=None, value=None, holds_anything=False)
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)]))
        assert worth.undivided_pots == []

    @pytest.mark.asyncio
    async def test_an_unconvertible_pot_is_dropped_and_its_currency_reported(self, monkeypatch):
        # Fail-loud, the repo's standing rule: never sum a figure that could not be restated.
        _share(monkeypatch, nav=Decimal("100"), value=Decimal("50"), weights={"fci": Decimal("100")})
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat(_pot(currency="BRL"))], seats=[_seat(100)]))
        assert worth.pot_value == Decimal("0")
        assert worth.skipped_currencies == {"BRL"}


class TestTheAttribution:
    @pytest.mark.asyncio
    async def test_the_share_is_spread_over_the_segments_its_holdings_sit_in(self, monkeypatch):
        # Half of a pot that is 60% CEDEARs and 40% a bank account: 300 of cedears, 200 of cash.
        _share(
            monkeypatch,
            nav=Decimal("1000"),
            value=Decimal("500"),
            weights={"cedears": Decimal("600"), "cash": Decimal("400")},
        )
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)]))
        assert worth.buckets == {"cedears": Decimal("300.00"), "cash": Decimal("200.00")}

    @pytest.mark.asyncio
    async def test_the_segments_sum_to_the_share_exactly(self, monkeypatch):
        # Thirds of a share that does not divide: 33.33 x 3 = 99.99, and the odd cent goes to the
        # largest segment — here a three-way tie, broken on the lowest key so the same pot always
        # produces the same slices — so the donut adds up to the figure in the headline above it.
        _share(
            monkeypatch,
            nav=Decimal("300"),
            value=Decimal("100"),
            weights={"a": Decimal("100"), "b": Decimal("100"), "c": Decimal("100")},
        )
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)]))
        assert sum(worth.buckets.values()) == worth.pot_value == Decimal("100")
        assert worth.buckets["a"] == Decimal("33.34")

    @pytest.mark.asyncio
    async def test_the_conversion_happens_before_the_split(self, monkeypatch):
        # Converting each segment on its own and summing them is what leaves the parts a cent off the
        # whole. 50 USD of a pot valued in USD, displayed in ARS at 1000: 50,000 across two segments.
        _share(monkeypatch, nav=Decimal("100"), value=Decimal("50"), weights={"fci": Decimal("50"), "cash": Decimal("50")})
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)]), currency="ARS")
        assert worth.pot_value == Decimal("50000")
        assert sum(worth.buckets.values()) == Decimal("50000")


class TestTheBalanceSplit:
    @pytest.mark.asyncio
    async def test_owed_and_owing_are_reported_GROSS_not_netted(self, monkeypatch):
        # D3: each is its own net-worth line. Owed 100 in one group and owing 100 in another is not
        # somebody with no balances — the totals still net to zero in the headline, and the breakdown
        # says what the zero is made of.
        positions = _standing({10: {"USD": {100: Decimal("100")}}, 11: {"USD": {200: Decimal("-100")}}})
        worth = await _worth(monkeypatch, _context(seats=[_seat(100, 10), _seat(200, 11)], positions=positions))
        assert worth.receivable == Decimal("100")
        assert worth.payable == Decimal("100")
        assert worth.total == Decimal("0")

    @pytest.mark.asyncio
    async def test_only_the_callers_OWN_seat_counts(self, monkeypatch):
        # The bucket holds every member's position; the dashboard is one person's net worth.
        positions = _standing({10: {"USD": {100: Decimal("75"), 101: Decimal("-75")}}})
        worth = await _worth(monkeypatch, _context(seats=[_seat(100)], positions=positions))
        assert worth.receivable == Decimal("75")
        assert worth.payable == Decimal("0")

    @pytest.mark.asyncio
    async def test_currencies_never_net_against_each_other(self, monkeypatch):
        # Owing dollars while being owed pesos is a real state. Each bucket is converted on its own and
        # its SIGN decides which side it lands on, so the two do not cancel before they are reported.
        positions = _standing({10: {"USD": {100: Decimal("-10")}, "ARS": {100: Decimal("10000")}}})
        worth = await _worth(monkeypatch, _context(seats=[_seat(100)], positions=positions))
        assert worth.receivable == Decimal("10")
        assert worth.payable == Decimal("10")

    @pytest.mark.asyncio
    async def test_an_unconvertible_bucket_is_dropped_and_reported(self, monkeypatch):
        positions = _standing({10: {"BRL": {100: Decimal("500")}}})
        worth = await _worth(monkeypatch, _context(seats=[_seat(100)], positions=positions))
        assert worth.receivable == Decimal("0")
        assert worth.skipped_currencies == {"BRL"}

    @pytest.mark.asyncio
    async def test_a_payable_larger_than_the_pots_makes_the_total_negative(self, monkeypatch):
        # Somebody who owes more than their share of everything shared is worth less for it, and the
        # headline has to say so rather than clamping at zero.
        _share(monkeypatch, nav=Decimal("100"), value=Decimal("100"), weights={"fci": Decimal("100")})
        positions = _standing({10: {"USD": {100: Decimal("-250")}}})
        worth = await _worth(monkeypatch, _context(pots=[_pot_seat()], seats=[_seat(100)], positions=positions))
        assert worth.total == Decimal("-150")


class TestHasShared:
    @pytest.mark.asyncio
    async def test_a_solo_user_has_no_shared_side_and_pays_for_no_reads(self, monkeypatch):
        _share(monkeypatch, nav=Decimal("1"), value=Decimal("1"))
        worth = await _worth(monkeypatch, _context())
        assert worth.has_shared is False
        assert worth.total == Decimal("0")
        pot_service.get_member_share.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_seat_with_no_money_at_all_still_has_a_shared_side(self, monkeypatch):
        # Existence, not value: a household whose balances happen to be square this week still gets
        # the breakdown, exactly as has_holdings is an existence test rather than a non-zero one.
        worth = await _worth(monkeypatch, _context(seats=[_seat(100)]))
        assert worth.has_shared is True
        assert worth.total == Decimal("0")


class TestTheEarliestMonth:
    def test_a_pots_anchor_is_its_first_event(self):
        context = _context(pots=[_pot_seat(events=[_event(date(2025, 3, 4))])])
        assert shared_worth_service.earliest_month(context) == (2025, 3)

    def test_a_pot_with_no_ledger_anchors_at_its_creation(self):
        assert shared_worth_service.earliest_month(_context(pots=[_pot_seat()])) == (2026, 1)

    def test_the_flow_rows_count_too(self):
        context = _context(pots=[_pot_seat()], positions=[((2025, 11), {})])
        assert shared_worth_service.earliest_month(context) == (2025, 11)

    def test_nothing_shared_has_no_earliest_month(self):
        assert shared_worth_service.earliest_month(_context(seats=[_seat(100)])) is None


class TestTheSeries:
    @pytest.mark.asyncio
    async def test_each_point_takes_the_pots_share_at_that_point(self, monkeypatch):
        points = [
            PotValueSeriesPoint(date=date(2026, 6, 30), nav=Decimal("200"), my_value=Decimal("100")),
            PotValueSeriesPoint(date=date(2026, 7, 31), nav=Decimal("400"), my_value=Decimal("200")),
        ]
        monkeypatch.setattr(pot_service, "compute_share_series", AsyncMock(return_value=points))
        values, skipped = await shared_worth_service.get_shared_series(
            AsyncMock(),
            1,
            _context(pots=[_pot_seat()], seats=[_seat(100)]),
            months=[(2026, 6), (2026, 7)],
            month_ends=[date(2026, 6, 30), date(2026, 7, 31)],
            currency="USD",
            lookup=_FixedLookup(),
        )
        assert values == [Decimal("100"), Decimal("200")]
        assert skipped == set()

    @pytest.mark.asyncio
    async def test_every_pot_is_added_rather_than_the_last_one_winning(self, monkeypatch):
        # A one-pot fixture cannot tell `+=` from `=`, and a mutation sweep proved it: the point has to
        # be the SUM of what the reader holds across pots, not whichever pot the loop ended on.
        series = {
            5: [PotValueSeriesPoint(date=date(2026, 7, 31), nav=Decimal("400"), my_value=Decimal("200"))],
            6: [PotValueSeriesPoint(date=date(2026, 7, 31), nav=Decimal("60"), my_value=Decimal("30"))],
        }
        monkeypatch.setattr(
            pot_service,
            "compute_share_series",
            AsyncMock(side_effect=lambda _s, pot, *_a, **_k: series[pot.id]),
        )
        context = _context(pots=[_pot_seat(_pot(5)), _pot_seat(_pot(6))], seats=[_seat(100)])
        values, _ = await shared_worth_service.get_shared_series(
            AsyncMock(),
            1,
            context,
            months=[(2026, 7)],
            month_ends=[date(2026, 7, 31)],
            currency="USD",
            lookup=_FixedLookup(),
        )
        assert values == [Decimal("230")]

    @pytest.mark.asyncio
    async def test_an_unknown_share_contributes_zero_rather_than_blanking_the_point(self, monkeypatch):
        # Deliberately unlike the NAV's own refusal rule: a net-worth line missing one person's share
        # of one pot is still the honest answer for everything else they hold, and blanking it would
        # hide a whole private portfolio because a co-owner forgot a snapshot.
        points = [
            PotValueSeriesPoint(date=date(2026, 6, 30), nav=None, my_value=None),
            PotValueSeriesPoint(date=date(2026, 7, 31), nav=Decimal("400"), my_value=Decimal("200")),
        ]
        monkeypatch.setattr(pot_service, "compute_share_series", AsyncMock(return_value=points))
        values, _ = await shared_worth_service.get_shared_series(
            AsyncMock(),
            1,
            _context(pots=[_pot_seat()], seats=[_seat(100)]),
            months=[(2026, 6), (2026, 7)],
            month_ends=[date(2026, 6, 30), date(2026, 7, 31)],
            currency="USD",
            lookup=_FixedLookup(),
        )
        assert values == [Decimal("0"), Decimal("200")]

    @pytest.mark.asyncio
    async def test_positions_forward_fill_over_months_that_did_not_move(self, monkeypatch):
        # The positions series carries only the months that moved, so a quiet month has to stand where
        # the previous one left it — a balance does not disappear because nobody recorded anything.
        monkeypatch.setattr(pot_service, "compute_share_series", AsyncMock(return_value=[]))
        context = _context(
            seats=[_seat(100)],
            positions=[((2026, 5), {10: {"USD": {100: Decimal("40")}}}), ((2026, 7), {10: {"USD": {100: Decimal("90")}}})],
        )
        values, _ = await shared_worth_service.get_shared_series(
            AsyncMock(),
            1,
            context,
            months=[(2026, 4), (2026, 5), (2026, 6), (2026, 7)],
            month_ends=[date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31)],
            currency="USD",
            lookup=_FixedLookup(),
        )
        # April predates the first row (square), May opens at 40, June holds it, July moves to 90.
        assert values == [Decimal("0"), Decimal("40"), Decimal("40"), Decimal("90")]

    @pytest.mark.asyncio
    async def test_the_last_point_equals_what_the_headline_reports(self, monkeypatch):
        # THE parity test for the balance half: the chart's final point and the Shared figure above it
        # are two derivations of one number, and a reader compares them at a glance. Both are driven
        # from the same position fixture here, so a sign flip or a dropped seat reddens.
        by_group = {10: {"USD": {100: Decimal("90")}, "ARS": {100: Decimal("-20000")}}}
        _share(monkeypatch, nav=Decimal("1"), value=None, holds_anything=False)
        context = _context(seats=[_seat(100)], positions=_standing(by_group))
        worth = await _worth(monkeypatch, context)

        monkeypatch.setattr(pot_service, "compute_share_series", AsyncMock(return_value=[]))
        values, _ = await shared_worth_service.get_shared_series(
            AsyncMock(),
            1,
            context,
            months=[(2026, 7)],
            month_ends=[date(2026, 7, 31)],
            currency="USD",
            lookup=_FixedLookup(),
        )
        assert values[-1] == worth.total == Decimal("70")
