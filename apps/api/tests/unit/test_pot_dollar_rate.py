# A pot's dollar rate: every shared figure converts at the POT's rate, and only the last step into a
# reader's own display currency follows that reader's preference.
#
# Built on real RateLookups over one day of three USD/ARS quotes — oficial 1000, MEP 1200, blue 1500 — so
# each rate gives a different answer and a figure names the rate it was converted at. The repositories
# are stubbed; the valuation engine, the unit maths and the conversions all run for real.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    GroupAdminRequiredError,
    NotFoundError,
    PotDollarRateAlreadyAgreedError,
    PotDollarRateNotYoursError,
    PotDollarRateOwnerRequiredError,
    PotDollarRateProposalPendingError,
    PotDollarRateUnchangedError,
)
from app.domain.currency import RatePoint
from app.models.asset_price import AssetPrice
from app.models.exchange_rate import DollarRate, ExchangeRatePair
from app.models.group import GroupMember, GroupMemberRole
from app.models.investment import Investment, InvestmentCategory
from app.models.pot import OwnershipEventType, Pot, PotMemberPermission, PotOwnershipEvent, PotVisibility
from app.models.snapshot import InvestmentSnapshot
from app.models.user import User
from app.services import asset_price_service, exchange_rate_service, pot_ownership_service, pot_service, shared_worth_service
from app.utils.metrics import RateLookup

DAY = date(2026, 6, 1)
RATES = {
    ExchangeRatePair.USD_ARS_OFICIAL: [RatePoint(date(2026, 1, 1), Decimal("1000"))],
    ExchangeRatePair.USD_ARS_MEP: [RatePoint(date(2026, 1, 1), Decimal("1200"))],
    ExchangeRatePair.USD_ARS_BLUE: [RatePoint(date(2026, 1, 1), Decimal("1500"))],
}

# Two members whose personal preferences differ from each other and from the pot's MEP.
ANA = User(id=1, name="Ana", email="a@test", password_hash="x", session_epoch=0)
BRUNO = User(id=2, name="Bruno", email="b@test", password_hash="x", session_epoch=0)
PREFERENCES = {ANA.id: "blue", BRUNO.id: "oficial"}
ANA_SEAT = GroupMember(id=100, group_id=10, user_id=ANA.id, display_name="Ana", role=GroupMemberRole.admin)
BRUNO_SEAT = GroupMember(id=101, group_id=10, user_id=BRUNO.id, display_name="Bruno", role=GroupMemberRole.member)
SEATS = {ANA.id: ANA_SEAT, BRUNO.id: BRUNO_SEAT}


def _pot(pot_id: int = 5, dollar_rate: DollarRate = DollarRate.mep) -> Pot:
    return Pot(id=pot_id, group_id=10, base_currency="USD", dollar_rate=dollar_rate, is_default=pot_id == 5)


# 50 units each at 1.00: the pot is split evenly between the two members.
def _openings(pot_id: int = 5) -> list[PotOwnershipEvent]:
    return [
        PotOwnershipEvent(
            id=member_id,
            pot_id=pot_id,
            type=OwnershipEventType.opening,
            date=date(2026, 1, 1),
            member_id=member_id,
            units=Decimal("50"),
            unit_price=Decimal("1"),
        )
        for member_id in (ANA_SEAT.id, BRUNO_SEAT.id)
    ]


def _investment(investment_id: int, currency: str, *, pot_id: int | None = 5, user_id: int | None = None) -> Investment:
    return Investment(
        id=investment_id, user_id=user_id, pot_id=pot_id, name=f"I{investment_id}", category=InvestmentCategory.fci, base_currency=currency
    )


def _snapshot(investment_id: int, value: str, currency: str) -> InvestmentSnapshot:
    return InvestmentSnapshot(
        id=investment_id, investment_id=investment_id, user_id=None, pot_id=None, date=date(2026, 1, 1), value=Decimal(value), currency=currency
    )


# Every stored rate, and each member's own preference, served the way the real service reads them — so
# a lookup built for a member carries that member's rate and one built for a pot carries the pot's.
def _rates(monkeypatch) -> None:
    monkeypatch.setattr(exchange_rate_service, "get_rates_grouped_by_pair_cached", AsyncMock(return_value=RATES))
    monkeypatch.setattr(exchange_rate_service.settings_service, "get_dollar_pref", AsyncMock(side_effect=lambda _s, user_id: PREFERENCES[user_id]))


# What the pots hold, keyed by investment id: each pot reads its own from `holdings`, and the snapshot
# read answers for whichever ids it is asked about.
def _holdings(monkeypatch, holdings: dict[int, list[Investment]], snapshots: dict[int, InvestmentSnapshot]) -> None:
    monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(side_effect=lambda _s, pot_id: holdings.get(pot_id, [])))
    monkeypatch.setattr(
        pot_service.pot_repository, "list_active_investments_by_pots", AsyncMock(side_effect=lambda _s, ids: {i: holdings.get(i, []) for i in ids})
    )
    monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(pot_service.pot_repository, "list_accounts_by_pots", AsyncMock(return_value={}))
    monkeypatch.setattr(
        pot_service.snapshot_repository,
        "get_latest_by_investments",
        AsyncMock(side_effect=lambda _s, ids, as_of_date: {i: snapshots[i] for i in ids if i in snapshots}),
    )
    series = AsyncMock(side_effect=lambda _s, ids, until: [snapshots[i] for i in ids])
    monkeypatch.setattr(pot_service.snapshot_repository, "list_by_investments", series)


# The reads get_pot makes besides the holdings: the visibility gate (a 'members' pot, so no permission
# row is needed), the roster, and the ledger.
def _pot_page(monkeypatch, pot: Pot, events: list[PotOwnershipEvent]) -> None:
    monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=pot))
    monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(side_effect=lambda _s, _g, user_id: SEATS[user_id]))
    monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=None))
    monkeypatch.setattr(pot_service.group_repository, "list_members", AsyncMock(return_value=list(SEATS.values())))
    monkeypatch.setattr(pot_service.pot_repository, "list_permissions", AsyncMock(return_value=[]))
    monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=events))


# The writes a dollar-rate change makes besides the pot row, captured: the audit trail and the two
# notification calls. Returns them as (audit, dispatch, dispatch_many).
def _agreement(monkeypatch) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    monkeypatch.setattr(pot_service.pot_repository, "lock", AsyncMock())
    monkeypatch.setattr(pot_service.pot_repository, "save", AsyncMock())
    monkeypatch.setattr(pot_service.group_repository, "get_by_id", AsyncMock(return_value=None))
    audit = AsyncMock()
    monkeypatch.setattr(pot_service.shared_audit_service, "record", audit)
    dispatch, dispatch_many = AsyncMock(), AsyncMock()
    monkeypatch.setattr(pot_service.notification_service, "dispatch", dispatch)
    monkeypatch.setattr(pot_service.notification_service, "dispatch_many", dispatch_many)
    return (audit, dispatch, dispatch_many)


class TestEveryMemberSeesTheSamePot:
    # A pot holding 1,200,000 ARS is worth 1,000 USD at its MEP rate. Ana prefers blue (800) and Bruno
    # oficial (1,200); before the setting each of them saw their own figure, and units were priced at it.

    @pytest.mark.asyncio
    async def test_two_members_with_different_preferences_see_one_nav_and_one_unit_price(self, monkeypatch):
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: [_investment(1, "ARS")]}, {1: _snapshot(1, "1200000", "ARS")})
        _pot_page(monkeypatch, _pot(), _openings())
        ana = await pot_service.get_pot(AsyncMock(), 5, ANA)
        bruno = await pot_service.get_pot(AsyncMock(), 5, BRUNO)
        assert (ana.nav, ana.unit_price) == (bruno.nav, bruno.unit_price) == (Decimal("1000"), Decimal("10"))
        assert ana.dollar_rate == DollarRate.mep
        assert [s.value for s in ana.shares] == [s.value for s in bruno.shares] == [Decimal("500.00"), Decimal("500.00")]

    @pytest.mark.asyncio
    async def test_the_value_series_is_the_same_for_both_members_too(self, monkeypatch):
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: [_investment(1, "ARS")]}, {1: _snapshot(1, "1200000", "ARS")})
        _pot_page(monkeypatch, _pot(), _openings())
        ana = await pot_service.get_value_series(AsyncMock(), 5, ANA, periods=3)
        bruno = await pot_service.get_value_series(AsyncMock(), 5, BRUNO, periods=3)
        assert [p.nav for p in ana.points] == [p.nav for p in bruno.points]
        assert {p.nav for p in ana.points} == {Decimal("1000")}

    @pytest.mark.asyncio
    async def test_each_pot_on_one_list_is_valued_at_its_own_rate(self, monkeypatch):
        # The group hub values every pot in one batch, from ONE loaded set of rates — and two pots on
        # different rates must still each get their own, so the batch converts per pot.
        _rates(monkeypatch)
        _holdings(
            monkeypatch,
            {5: [_investment(1, "ARS")], 6: [_investment(2, "ARS", pot_id=6)]},
            {1: _snapshot(1, "1200000", "ARS"), 2: _snapshot(2, "1200000", "ARS")},
        )
        pots = [_pot(5, DollarRate.mep), _pot(6, DollarRate.blue)]
        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", AsyncMock(return_value=pots))
        monkeypatch.setattr(pot_service.pot_repository, "list_permissions_by_pots", AsyncMock(return_value={}))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pots", AsyncMock(return_value={5: _openings(5), 6: _openings(6)}))
        monkeypatch.setattr(pot_service.group_repository, "list_members_by_groups", AsyncMock(return_value={10: list(SEATS.values())}))
        listed = await pot_service.list_pots(AsyncMock(), BRUNO, group_id=10)
        assert {p.id: p.nav for p in listed} == {5: Decimal("1000"), 6: Decimal("800")}


class TestUnitsAreIssuedAtThePotsRate:
    # The pot holds 1,000 USD in 100 units (a price of 10). Ana contributes a holding worth 600,000 ARS:
    # 500 USD at the pot's MEP rate, so 50 units — where her own blue preference would have issued 40 and
    # Bruno's oficial 60. The pot's own value is in dollars, so the rate cannot cancel out of the division.

    @staticmethod
    def _wire(monkeypatch, pot: Pot) -> AsyncMock:
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: [_investment(1, "USD")]}, {1: _snapshot(1, "1000", "USD"), 12: _snapshot(12, "600000", "ARS")})
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(pot, ANA_SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "lock", AsyncMock())
        holding = _investment(12, "ARS", pot_id=None, user_id=ANA.id)
        monkeypatch.setattr(pot_service, "require_contributable_holding", AsyncMock(return_value=holding))
        monkeypatch.setattr(pot_service, "attach_holding", AsyncMock())
        monkeypatch.setattr(pot_ownership_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=_openings()))
        # The real repository flushes to get an id, which the response needs.
        created = AsyncMock(side_effect=lambda _s, event: event.model_copy(update={"id": 900}))
        monkeypatch.setattr(pot_ownership_service.pot_ownership_repository, "create", created)
        monkeypatch.setattr(pot_ownership_service.shared_audit_service, "record", AsyncMock())
        monkeypatch.setattr(pot_service, "list_notifiable_user_ids", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_ownership_service.group_repository, "get_by_id", AsyncMock(return_value=None))
        monkeypatch.setattr(pot_ownership_service.notification_service, "dispatch", AsyncMock())
        return created

    @pytest.mark.asyncio
    async def test_a_contribution_is_valued_and_priced_at_the_pots_rate_not_the_contributors(self, monkeypatch):
        created = self._wire(monkeypatch, _pot())
        await pot_ownership_service.contribute_holding(AsyncMock(), 5, ANA, investment_id=12)
        event = created.await_args.args[1]
        assert (event.base_amount, event.unit_price, event.units) == (Decimal("500.00"), Decimal("10"), Decimal("50"))

    @pytest.mark.asyncio
    async def test_the_same_contribution_on_a_blue_pot_issues_what_blue_says(self, monkeypatch):
        # The control: the pot's rate is what moves the answer.
        created = self._wire(monkeypatch, _pot(dollar_rate=DollarRate.blue))
        await pot_ownership_service.contribute_holding(AsyncMock(), 5, ANA, investment_id=12)
        assert created.await_args.args[1].units == Decimal("40")

    @pytest.mark.asyncio
    async def test_a_withdrawal_is_priced_at_the_pots_rate_not_the_recorders(self, monkeypatch):
        # A take-out redeems units at the pot's price. This blue pot holds 1,200,000 ARS: 800 USD over
        # 100 units, so 100 USD out redeems 12.5 units — where MEP would say 10 and Bruno's own oficial,
        # who records it, 8.33.
        created = self._wire(monkeypatch, _pot(dollar_rate=DollarRate.blue))
        _holdings(monkeypatch, {5: [_investment(1, "ARS")]}, {1: _snapshot(1, "1200000", "ARS")})
        monkeypatch.setattr(pot_ownership_service.group_repository, "get_member", AsyncMock(return_value=ANA_SEAT))
        await pot_ownership_service.record_movement(
            AsyncMock(), 5, BRUNO, type=OwnershipEventType.withdrawal, date=DAY, member_id=ANA_SEAT.id, amount=Decimal("100")
        )
        assert created.await_args.args[1].units == Decimal("-12.5")


class TestChangingTheRateReachesFutureFiguresOnly:
    @pytest.mark.asyncio
    async def test_the_pot_is_revalued_at_the_new_rate_and_no_recorded_row_is_touched(self, monkeypatch):
        # Recorded at MEP: a contribution of 600,000 ARS credited as 500 USD for 50 units.
        recorded = PotOwnershipEvent(
            id=3,
            pot_id=5,
            type=OwnershipEventType.contribution,
            date=date(2026, 2, 1),
            member_id=ANA_SEAT.id,
            amount=Decimal("600000"),
            amount_currency="ARS",
            base_amount=Decimal("500"),
            units=Decimal("50"),
            unit_price=Decimal("10"),
        )
        events = [*_openings(), recorded]
        pot = _pot()
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: [_investment(1, "ARS")]}, {1: _snapshot(1, "1800000", "ARS")})
        _pot_page(monkeypatch, pot, events)
        _agreement(monkeypatch)
        writes = AsyncMock()
        for method in ("create", "create_many", "save", "delete"):
            monkeypatch.setattr(pot_service.pot_ownership_repository, method, writes, raising=False)

        before = await pot_service.get_pot(AsyncMock(), 5, ANA)
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        pending = await pot_service.get_pot(AsyncMock(), 5, ANA)
        await pot_service.agree_dollar_rate(AsyncMock(), 5, BRUNO)
        after = await pot_service.get_pot(AsyncMock(), 5, ANA)

        # 1,800,000 ARS: 1,500 USD at MEP, 1,200 at blue — over the same 150 units. Nothing moved while
        # the change waited for Bruno.
        assert (before.nav, pending.nav, after.nav) == (Decimal("1500"), Decimal("1500"), Decimal("1200"))
        assert after.dollar_rate == DollarRate.blue
        assert before.total_units == after.total_units == Decimal("150")
        # The recorded row is exactly what it was, and nothing wrote to the ledger.
        assert (recorded.base_amount, recorded.units, recorded.unit_price) == (Decimal("500"), Decimal("50"), Decimal("10"))
        writes.assert_not_awaited()


class TestTheViewerConvertsTheShareAtTheirOwnRate:
    # Ana's half of a pot holding 1,200,000 ARS is 500 USD at the pot's MEP rate. Shown in ARS on her
    # dashboard, at HER blue rate, it reads 750,000 — not 600,000, which is what MEP all the way and blue
    # all the way (400 USD) would both give. Only the last step is hers.

    @pytest.mark.asyncio
    async def test_the_share_is_valued_at_the_pots_rate_and_displayed_at_the_viewers(self, monkeypatch):
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: [_investment(1, "ARS")]}, {1: _snapshot(1, "1200000", "ARS")})
        seat = pot_service.PotSeat(pot=_pot(), member_id=ANA_SEAT.id, events=_openings())
        # The dashboard hands its own lookup to load_context, so the valuations are given the VIEWER's
        # lookup too — and must still convert at the pot's rate.
        viewer = await exchange_rate_service.get_user_rate_lookup(AsyncMock(), ANA.id)
        context = shared_worth_service.SharedContext(seats=[], pots=[seat], positions=[], lookup=viewer)
        worth = await shared_worth_service.get_shared_worth(AsyncMock(), context, currency="ARS", lookup=viewer, as_of_date=DAY)
        assert worth.pot_value == Decimal("750000.00")

    @pytest.mark.asyncio
    async def test_the_chart_converts_each_point_the_same_way(self, monkeypatch):
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: [_investment(1, "ARS")]}, {1: _snapshot(1, "1200000", "ARS")})
        monkeypatch.setattr(pot_service.account_service, "compute_account_balance_series", AsyncMock(return_value={}))
        seat = pot_service.PotSeat(pot=_pot(), member_id=ANA_SEAT.id, events=_openings())
        viewer = await exchange_rate_service.get_user_rate_lookup(AsyncMock(), ANA.id)
        context = shared_worth_service.SharedContext(seats=[], pots=[seat], positions=[], lookup=viewer)
        values, skipped = await shared_worth_service.get_shared_series(
            AsyncMock(), context, months=[(2026, 5), (2026, 6)], month_ends=[date(2026, 5, 31), date(2026, 6, 30)], currency="ARS", lookup=viewer
        )
        assert values == [Decimal("750000.00"), Decimal("750000.00")]
        assert not skipped


class TestTheRateLookupForAPreference:
    def test_it_reads_the_same_rates_under_the_other_preference(self):
        mine = RateLookup("blue", RATES)
        assert mine.get_rate_map_at(DAY)["ARS"] == Decimal("1500")
        assert mine.for_dollar_preference("mep").get_rate_map_at(DAY)["ARS"] == Decimal("1200")
        assert mine.for_dollar_preference("oficial").get_rate_map_at(DAY)["ARS"] == Decimal("1000")

    def test_it_is_the_same_lookup_for_its_own_preference_and_memoised_for_another(self):
        mine = RateLookup("blue", RATES)
        assert mine.for_dollar_preference("blue") is mine
        assert mine.for_dollar_preference("mep") is mine.for_dollar_preference("mep")


# Two more seats for the agreement rules: Carla, a third owner with an account, and two seats that can
# never answer — a name-only placeholder and a member who has left the group.
CARLA = User(id=3, name="Carla", email="c@test", password_hash="x", session_epoch=0)
CARLA_SEAT = GroupMember(id=102, group_id=10, user_id=CARLA.id, display_name="Carla", role=GroupMemberRole.member)
NAME_ONLY_SEAT = GroupMember(id=103, group_id=10, user_id=None, display_name="Abuela", role=GroupMemberRole.member)
LEFT_SEAT = GroupMember(id=104, group_id=10, user_id=4, display_name="Diego", role=GroupMemberRole.member, is_active=False)


def _units(*holders: tuple[int, str]) -> list[PotOwnershipEvent]:
    return [
        PotOwnershipEvent(
            id=member_id,
            pot_id=5,
            type=OwnershipEventType.opening,
            date=date(2026, 1, 1),
            member_id=member_id,
            units=Decimal(units),
            unit_price=Decimal("1"),
        )
        for member_id, units in holders
    ]


class TestTheOwnersAgree:
    # A pot's dollar rate decides what every share is worth and what units are issued at, so it changes
    # by the OWNERS' agreement: one proposes, the others agree, and nothing changes until all have.

    @staticmethod
    def _wire(
        monkeypatch, pot: Pot, events: list[PotOwnershipEvent], seats: list[GroupMember], permissions: dict[int, PotMemberPermission] | None = None
    ) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
        by_user = {seat.user_id: seat for seat in seats if seat.user_id is not None}
        rows = permissions or {}
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=pot))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(side_effect=lambda _s, _g, user_id: by_user[user_id]))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(side_effect=lambda _s, _p, member_id: rows.get(member_id)))
        monkeypatch.setattr(pot_service.group_repository, "list_members", AsyncMock(return_value=seats))
        monkeypatch.setattr(pot_service.pot_repository, "list_permissions", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=events))
        # The response is get_pot's, covered elsewhere; these tests read the pot row and the side effects.
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock())
        return _agreement(monkeypatch)

    @staticmethod
    def _payloads(audit: AsyncMock) -> list[tuple[str, dict]]:
        return [(call.kwargs["action"].value, call.kwargs["payload"]) for call in audit.await_args_list]

    @staticmethod
    def _readers(dispatch_many: AsyncMock) -> dict[str, list[int]]:
        return {item.payload["variant"]: item.user_ids for item in dispatch_many.await_args.args[1]}

    @pytest.mark.asyncio
    async def test_a_lone_owner_changes_it_at_once_and_the_change_is_recorded_from_and_to(self, monkeypatch):
        pot = _pot()
        audit, _, _ = self._wire(monkeypatch, pot, _units((ANA_SEAT.id, "100")), [ANA_SEAT, BRUNO_SEAT])
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        assert (pot.dollar_rate, pot.dollar_rate_proposal) == (DollarRate.blue, None)
        assert self._payloads(audit) == [("updated", {"pot": None, "variant": "dollar_rate", "from_rate": "mep", "to_rate": "blue"})]

    @pytest.mark.asyncio
    async def test_nothing_changes_until_every_owner_has_agreed(self, monkeypatch):
        pot = _pot()
        seats = [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT]
        audit, dispatch, dispatch_many = self._wire(monkeypatch, pot, _units((100, "50"), (101, "25"), (102, "25")), seats)

        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        assert (pot.dollar_rate, pot.dollar_rate_proposal, pot.dollar_rate_agreed_by) == (DollarRate.mep, DollarRate.blue, [100])
        # Every other owner hears that it needs their agreement.
        assert dispatch.await_args.args[1] == [BRUNO.id, CARLA.id]
        assert dispatch.await_args.args[2]["variant"] == "dollar_rate_proposed_to_you"

        await pot_service.agree_dollar_rate(AsyncMock(), 5, BRUNO)
        assert (pot.dollar_rate, pot.dollar_rate_agreed_by) == (DollarRate.mep, [100, 101])
        dispatch_many.assert_not_awaited()

        await pot_service.agree_dollar_rate(AsyncMock(), 5, CARLA)
        assert (pot.dollar_rate, pot.dollar_rate_proposal, pot.dollar_rate_agreed_by) == (DollarRate.blue, None, [])
        # The proposer reads that everyone agreed to theirs; the other owners that the pot now uses it.
        # Carla gave the last agreement, so she is not told about her own act.
        assert self._readers(dispatch_many) == {"dollar_rate_applied_from_you": [ANA.id], "dollar_rate_applied_to_you": [BRUNO.id]}
        assert [action for action, _ in self._payloads(audit)] == ["updated", "confirmed", "confirmed", "updated"]
        assert self._payloads(audit)[-1][1] == {"pot": None, "variant": "dollar_rate", "from_rate": "mep", "to_rate": "blue"}

    @pytest.mark.asyncio
    async def test_a_member_who_owns_nothing_can_neither_propose_nor_agree(self, monkeypatch):
        pot = _pot()
        self._wire(monkeypatch, pot, _units((ANA_SEAT.id, "100")), [ANA_SEAT, BRUNO_SEAT])
        with pytest.raises(PotDollarRateOwnerRequiredError):
            await pot_service.propose_dollar_rate(AsyncMock(), 5, BRUNO, dollar_rate=DollarRate.blue)
        pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by = DollarRate.blue, ANA_SEAT.id, [ANA_SEAT.id]
        with pytest.raises(PotDollarRateOwnerRequiredError):
            await pot_service.agree_dollar_rate(AsyncMock(), 5, BRUNO)
        assert pot.dollar_rate == DollarRate.mep

    @pytest.mark.asyncio
    async def test_before_anybody_owns_anything_a_group_admin_sets_it(self, monkeypatch):
        pot = _pot()
        self._wire(monkeypatch, pot, [], [ANA_SEAT, BRUNO_SEAT])

        async def require_admin(_s, _g, user):
            if user.id != ANA.id:
                raise GroupAdminRequiredError()

        monkeypatch.setattr("app.services.group_service.require_admin", require_admin)
        with pytest.raises(GroupAdminRequiredError):
            await pot_service.propose_dollar_rate(AsyncMock(), 5, BRUNO, dollar_rate=DollarRate.blue)
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        assert pot.dollar_rate == DollarRate.blue

    @pytest.mark.asyncio
    async def test_a_seat_that_can_never_answer_is_not_waited_for(self, monkeypatch):
        # The same posture a change of split takes: a name-only seat, or one that left, can never agree,
        # so waiting for it would make the rate unchangeable for good.
        pot = _pot()
        seats = [ANA_SEAT, NAME_ONLY_SEAT, LEFT_SEAT]
        self._wire(monkeypatch, pot, _units((100, "50"), (103, "25"), (104, "25")), seats)
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.oficial)
        assert (pot.dollar_rate, pot.dollar_rate_proposal) == (DollarRate.oficial, None)

    @pytest.mark.asyncio
    async def test_only_the_proposer_withdraws_and_withdrawing_changes_nothing(self, monkeypatch):
        pot = _pot()
        audit, _, _ = self._wire(monkeypatch, pot, _units((100, "50"), (101, "50")), [ANA_SEAT, BRUNO_SEAT])
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        with pytest.raises(PotDollarRateNotYoursError):
            await pot_service.withdraw_dollar_rate(AsyncMock(), 5, BRUNO)
        await pot_service.withdraw_dollar_rate(AsyncMock(), 5, ANA)
        assert (pot.dollar_rate, pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by) == (DollarRate.mep, None, None, [])
        assert self._payloads(audit)[-1] == ("updated", {"pot": None, "variant": "dollar_rate_withdrawn", "from_rate": "mep", "to_rate": "blue"})

    @pytest.mark.asyncio
    async def test_a_proposal_whose_proposer_left_can_be_withdrawn_by_an_owner(self, monkeypatch):
        pot = _pot()
        pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by = DollarRate.blue, LEFT_SEAT.id, [LEFT_SEAT.id]
        self._wire(monkeypatch, pot, _units((101, "50"), (104, "50")), [BRUNO_SEAT, LEFT_SEAT])
        await pot_service.withdraw_dollar_rate(AsyncMock(), 5, BRUNO)
        assert pot.dollar_rate_proposal is None

    @pytest.mark.asyncio
    async def test_one_proposal_at_a_time_and_never_to_the_rate_in_force(self, monkeypatch):
        pot = _pot()
        self._wire(monkeypatch, pot, _units((100, "50"), (101, "50")), [ANA_SEAT, BRUNO_SEAT])
        with pytest.raises(PotDollarRateUnchangedError):
            await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.mep)
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        with pytest.raises(PotDollarRateProposalPendingError):
            await pot_service.propose_dollar_rate(AsyncMock(), 5, BRUNO, dollar_rate=DollarRate.oficial)

    @pytest.mark.asyncio
    async def test_agreeing_twice_is_refused_until_nobody_is_left_to_wait_for(self, monkeypatch):
        pot = _pot()
        events = _units((100, "50"), (101, "50"))
        self._wire(monkeypatch, pot, events, [ANA_SEAT, BRUNO_SEAT])
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        with pytest.raises(PotDollarRateAlreadyAgreedError):
            await pot_service.agree_dollar_rate(AsyncMock(), 5, ANA)
        # Bruno sells his whole stake to Ana while it waits: nobody is left to agree, and Ana's call applies it.
        events.append(
            PotOwnershipEvent(
                id=9,
                pot_id=5,
                type=OwnershipEventType.reagreement,
                date=date(2026, 3, 1),
                member_id=101,
                counterparty_member_id=100,
                units=Decimal("-50"),
                unit_price=Decimal("1"),
            )
        )
        await pot_service.agree_dollar_rate(AsyncMock(), 5, ANA)
        assert pot.dollar_rate == DollarRate.blue

    # An owner's say on the rate does not depend on seeing the pot. Hidden either way — an explicit row
    # with can_view false, or an 'owners' pot with no row of their own — Bruno still holds half of it: he
    # is asked, reads the proposal, and his agreement is what applies it. Nothing else about the pot
    # reaches him through this surface.
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("visibility", "permissions"),
        [
            (PotVisibility.members, {101: PotMemberPermission(pot_id=5, member_id=101, can_view=False)}),
            (PotVisibility.owners, {100: PotMemberPermission(pot_id=5, member_id=100, can_view=True, can_write=True)}),
        ],
        ids=["can_view_false", "owners_pot_without_a_row"],
    )
    async def test_an_owner_hidden_from_the_pot_is_asked_and_can_agree(self, monkeypatch, visibility, permissions):
        pot = _pot()
        pot.visibility = visibility
        _, dispatch, _ = self._wire(monkeypatch, pot, _units((100, "50"), (101, "50")), [ANA_SEAT, BRUNO_SEAT], permissions)
        assert not pot_service._may_view(pot, permissions.get(BRUNO_SEAT.id))

        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        assert dispatch.await_args.args[1] == [BRUNO.id]
        seen = await pot_service.get_dollar_rate(AsyncMock(), 5, BRUNO)
        assert (seen.dollar_rate_proposal.waiting_on, seen.dollar_rate_proposal.can_agree) == (["Bruno"], True)
        await pot_service.agree_dollar_rate(AsyncMock(), 5, BRUNO)
        assert pot.dollar_rate == DollarRate.blue

    @pytest.mark.asyncio
    async def test_a_hidden_member_who_owns_nothing_learns_nothing(self, monkeypatch):
        pot = _pot()
        hidden = {102: PotMemberPermission(pot_id=5, member_id=102, can_view=False)}
        self._wire(monkeypatch, pot, _units((100, "50"), (101, "50")), [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT], hidden)
        pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by = DollarRate.blue, ANA_SEAT.id, [ANA_SEAT.id]
        with pytest.raises(NotFoundError):
            await pot_service.get_dollar_rate(AsyncMock(), 5, CARLA)
        with pytest.raises(NotFoundError):
            await pot_service.agree_dollar_rate(AsyncMock(), 5, CARLA)

    @pytest.mark.asyncio
    async def test_when_every_unit_sits_with_seats_that_cannot_answer_an_admin_sets_it(self, monkeypatch):
        # Nobody could ever propose otherwise: the owners left, or never had an account.
        pot = _pot()
        audit, _, _ = self._wire(monkeypatch, pot, _units((103, "50"), (104, "50")), [ANA_SEAT, BRUNO_SEAT, NAME_ONLY_SEAT, LEFT_SEAT])

        async def require_admin(_s, _g, user):
            if user.id != ANA.id:
                raise GroupAdminRequiredError()

        monkeypatch.setattr("app.services.group_service.require_admin", require_admin)
        with pytest.raises(GroupAdminRequiredError):
            await pot_service.propose_dollar_rate(AsyncMock(), 5, BRUNO, dollar_rate=DollarRate.blue)
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        assert pot.dollar_rate == DollarRate.blue
        assert self._payloads(audit)[-1] == ("updated", {"pot": None, "variant": "dollar_rate", "from_rate": "mep", "to_rate": "blue"})

    @pytest.mark.asyncio
    async def test_a_proposal_applies_once_the_last_owner_it_waited_for_sells_out(self, monkeypatch):
        pot = _pot()
        pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by = DollarRate.blue, ANA_SEAT.id, [ANA_SEAT.id]
        # The ledger as it stands after Bruno's buy-out: Ana owns it all.
        _, _, dispatch_many = self._wire(monkeypatch, pot, _units((100, "100")), [ANA_SEAT, BRUNO_SEAT])
        await pot_service.after_ledger_change(AsyncMock(), pot, BRUNO, units_before={100: Decimal("50"), 101: Decimal("50")})
        assert (pot.dollar_rate, pot.dollar_rate_proposal) == (DollarRate.blue, None)
        assert self._readers(dispatch_many)["dollar_rate_applied_from_you"] == [ANA.id]

    @pytest.mark.asyncio
    async def test_a_member_who_becomes_an_owner_while_it_waits_is_asked(self, monkeypatch):
        pot = _pot()
        pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by = DollarRate.blue, ANA_SEAT.id, [ANA_SEAT.id]
        _, dispatch, _ = self._wire(monkeypatch, pot, _units((100, "40"), (101, "40"), (102, "20")), [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT])
        await pot_service.after_ledger_change(AsyncMock(), pot, CARLA, units_before={100: Decimal("50"), 101: Decimal("50")})
        assert pot.dollar_rate == DollarRate.mep
        # Carla is new and asked; Bruno was asked when it was proposed and is not asked twice.
        assert dispatch.await_args.args[1] == [CARLA.id]
        assert (dispatch.await_args.args[2]["variant"], dispatch.await_args.args[2]["actor"]) == ("dollar_rate_proposed_to_you", "Ana")

    @pytest.mark.asyncio
    async def test_the_owners_hear_when_a_proposal_is_withdrawn(self, monkeypatch):
        pot = _pot()
        _, dispatch, _ = self._wire(monkeypatch, pot, _units((100, "40"), (101, "40"), (102, "20")), [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT])
        await pot_service.propose_dollar_rate(AsyncMock(), 5, ANA, dollar_rate=DollarRate.blue)
        await pot_service.withdraw_dollar_rate(AsyncMock(), 5, ANA)
        assert dispatch.await_args.args[1] == [BRUNO.id, CARLA.id]
        assert dispatch.await_args.args[2]["variant"] == "dollar_rate_withdrawn_to_you"

    @pytest.mark.asyncio
    async def test_the_response_says_who_it_waits_on_and_what_each_reader_may_do(self, monkeypatch):
        pot = _pot()
        pot.dollar_rate_proposal, pot.dollar_rate_proposed_by, pot.dollar_rate_agreed_by = DollarRate.blue, ANA_SEAT.id, [ANA_SEAT.id]
        _rates(monkeypatch)
        _holdings(monkeypatch, {5: []}, {})
        _pot_page(monkeypatch, pot, _openings())
        ana = await pot_service.get_pot(AsyncMock(), 5, ANA)
        bruno = await pot_service.get_pot(AsyncMock(), 5, BRUNO)
        assert (ana.dollar_rate_proposal.proposed_by, ana.dollar_rate_proposal.waiting_on) == ("Ana", ["Bruno"])
        assert (ana.dollar_rate_proposal.can_agree, ana.dollar_rate_proposal.can_withdraw) == (False, True)
        assert (bruno.dollar_rate_proposal.can_agree, bruno.dollar_rate_proposal.can_withdraw) == (True, False)
        # Nobody proposes a second change while one waits.
        assert (ana.can_change_dollar_rate, bruno.can_change_dollar_rate) == (False, False)


class TestAPotInvestmentsPricePrefill:
    # The snapshot form prefills a price converted into the investment's currency. For a pot's investment
    # that figure becomes a snapshot every owner's share is valued from, so it converts at the POT's rate
    # (blue here) rather than at the person typing it's own (MEP).

    @staticmethod
    def _wire(monkeypatch, investment: Investment | None) -> None:
        _rates(monkeypatch)
        monkeypatch.setitem(PREFERENCES, ANA.id, "mep")
        price = AssetPrice(ticker="GGAL", date=date(2026, 1, 5), price=Decimal("1"), currency="USD", source="test")
        monkeypatch.setattr(asset_price_service, "get_or_fetch_price", AsyncMock(return_value=price))
        monkeypatch.setattr(asset_price_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=investment))
        monkeypatch.setattr(asset_price_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot(dollar_rate=DollarRate.blue)))

    @staticmethod
    async def _prefill(investment_id: int | None) -> Decimal | None:
        result = await asset_price_service.lookup_price(
            AsyncMock(), ANA.id, "GGAL", InvestmentCategory.stocks, date(2026, 1, 5), convert_to="ARS", investment_id=investment_id
        )
        return result.converted_price

    @pytest.mark.asyncio
    async def test_a_pot_investment_converts_at_the_pots_rate(self, monkeypatch):
        self._wire(monkeypatch, _investment(1, "ARS"))
        assert await self._prefill(1) == Decimal("1500")

    @pytest.mark.asyncio
    async def test_a_private_investment_converts_at_the_callers_own_rate(self, monkeypatch):
        self._wire(monkeypatch, _investment(1, "ARS", pot_id=None, user_id=ANA.id))
        assert await self._prefill(1) == Decimal("1200")
        assert await self._prefill(None) == Decimal("1200")
