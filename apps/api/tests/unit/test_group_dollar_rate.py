# A group's dollar rate: settling up converts at the GROUP's rate whoever records the payment, and a
# change of that rate takes every active member's agreement.
#
# The conversions run on real RateLookups over one day of three USD/ARS quotes — oficial 1000, MEP 1200,
# blue 1500 — so each rate gives a different answer and a figure names the rate it was converted at. The
# repositories are stubbed; the waterfall, the balance fold and the agreement rule all run for real.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    GroupDollarRateAlreadyAgreedError,
    GroupDollarRateNotYoursError,
    GroupDollarRateProposalPendingError,
    GroupDollarRateUnchangedError,
    GroupMemberOwnsPotError,
    NotFoundError,
    dollar_rate_consent,
)
from app.domain.currency import RatePoint
from app.models.exchange_rate import DollarRate, ExchangeRatePair
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_money_settings import GroupMoneySettings
from app.models.notification import NotificationEvent
from app.models.pot import OwnershipEventType, PotOwnershipEvent
from app.models.user import User
from app.services import exchange_rate_service, group_money_service, group_service, group_settlement_service, pot_service

DAY = date(2026, 6, 1)
RATES = {
    ExchangeRatePair.USD_ARS_OFICIAL: [RatePoint(date(2026, 1, 1), Decimal("1000"))],
    ExchangeRatePair.USD_ARS_MEP: [RatePoint(date(2026, 1, 1), Decimal("1200"))],
    ExchangeRatePair.USD_ARS_BLUE: [RatePoint(date(2026, 1, 1), Decimal("1500"))],
}
GROUP_ID = 10
GROUP = Group(id=GROUP_ID, name="Casa", kind=GroupKind.household)

ANA = User(id=1, name="Ana", email="a@test", password_hash="x", session_epoch=0)
BRUNO = User(id=2, name="Bruno", email="b@test", password_hash="x", session_epoch=0)
CARLA = User(id=3, name="Carla", email="c@test", password_hash="x", session_epoch=0)
# Personal preferences that differ from each other and from any group rate below, so a figure that
# followed a person rather than the group would say so.
PREFERENCES = {ANA.id: "oficial", BRUNO.id: "mep", CARLA.id: "oficial"}


def _seat(seat_id: int, user_id: int | None, name: str, *, active: bool = True, admin: bool = False) -> GroupMember:
    return GroupMember(
        id=seat_id,
        group_id=GROUP_ID,
        user_id=user_id,
        display_name=name,
        role=GroupMemberRole.admin if admin else GroupMemberRole.member,
        is_active=active,
    )


ANA_SEAT = _seat(100, ANA.id, "Ana", admin=True)
BRUNO_SEAT = _seat(101, BRUNO.id, "Bruno")
CARLA_SEAT = _seat(102, CARLA.id, "Carla")
NAME_ONLY_SEAT = _seat(103, None, "Abuela")
LEFT_SEAT = _seat(104, 4, "Diego", active=False)


# Real rate lookups: the stored rates are the three above, and a person's preference is the one listed.
# Asking for a person's own lookup is how a figure would follow them, so it stays available — the tests
# assert it is not what the group's figures read.
def _wire_rates(monkeypatch) -> None:
    monkeypatch.setattr(exchange_rate_service, "get_rates_grouped_by_pair_cached", AsyncMock(return_value=RATES))
    monkeypatch.setattr(exchange_rate_service.settings_service, "get_dollar_pref", AsyncMock(side_effect=lambda _s, user_id: PREFERENCES[user_id]))


# --- The agreement rule, shared with pots ---


class TestTheAgreementRule:
    def test_a_change_waits_for_whoever_has_not_agreed(self):
        assert dollar_rate_consent.waiting_on({1, 2, 3}, {1}) == {2, 3}
        assert dollar_rate_consent.is_agreed({1, 2}, {1, 2}) is True
        assert dollar_rate_consent.is_agreed({1, 2}, {1}) is False

    def test_a_party_agrees_once_unless_nobody_is_left_to_wait_for(self):
        assert dollar_rate_consent.may_agree(2, {1, 2}, {1}) is True
        assert dollar_rate_consent.may_agree(1, {1, 2}, {1}) is False
        # The backstop: everyone still here has agreed, so any of them may apply it.
        assert dollar_rate_consent.may_agree(1, {1}, {1, 2}) is True
        # A seat the change does not wait for never may.
        assert dollar_rate_consent.may_agree(9, {1, 2}, {1}) is False

    def test_only_the_proposer_withdraws_while_they_can_still_act(self):
        assert dollar_rate_consent.may_withdraw(1, 1, {1, 2}, proposer_can_act=True) is True
        assert dollar_rate_consent.may_withdraw(2, 1, {1, 2}, proposer_can_act=True) is False
        assert dollar_rate_consent.may_withdraw(2, 1, {2}, proposer_can_act=False) is True
        # And then only a party it waits for, not anybody in the group.
        assert dollar_rate_consent.may_withdraw(9, 1, {2}, proposer_can_act=False) is False


# --- Settling up converts at the group's rate ---


# Ana owes Bruno 30,000 pesos and 10 dollars, and pays in dollars: the excess over the dollar bucket
# spills into the peso one at whatever the GROUP says a dollar is worth.
def _wire_waterfall(monkeypatch, group_rate: DollarRate) -> None:
    _wire_rates(monkeypatch)
    monkeypatch.setattr(group_settlement_service.group_service, "require_member", AsyncMock(return_value=(GROUP, ANA_SEAT)))
    monkeypatch.setattr(group_settlement_service.group_repository, "list_members", AsyncMock(return_value=[ANA_SEAT, BRUNO_SEAT]))
    monkeypatch.setattr(
        group_settlement_service.group_money_settings_repository,
        "get_by_group_id",
        AsyncMock(return_value=GroupMoneySettings(group_id=GROUP_ID, dollar_rate=group_rate)),
    )
    positions = {
        "ARS": {ANA_SEAT.id: Decimal("-30000"), BRUNO_SEAT.id: Decimal("30000")},
        "USD": {ANA_SEAT.id: Decimal("-10"), BRUNO_SEAT.id: Decimal("10")},
    }
    monkeypatch.setattr(group_settlement_service, "_positions_by_currency", AsyncMock(return_value=positions))


class TestTheWaterfallConvertsAtTheGroupsRate:
    @pytest.mark.parametrize(("group_rate", "cost"), [(DollarRate.blue, Decimal("20.00")), (DollarRate.oficial, Decimal("30.00"))])
    @pytest.mark.asyncio
    async def test_the_peso_bucket_costs_what_the_group_rate_says_not_what_the_payer_prefers(self, monkeypatch, group_rate, cost):
        # Ana prefers oficial (30 dollars clears 30,000 pesos); under a blue group the same debt costs 20.
        _wire_waterfall(monkeypatch, group_rate)
        plan = await group_settlement_service.preview_waterfall(
            AsyncMock(), GROUP_ID, ANA, from_member_id=ANA_SEAT.id, to_member_id=BRUNO_SEAT.id, date=DAY, amount=Decimal("40"), currency="USD"
        )
        assert [(bucket.currency, bucket.cost) for bucket in plan.buckets] == [("ARS", cost)]

    @pytest.mark.asyncio
    async def test_whoever_records_the_payment_gets_the_same_plan(self, monkeypatch):
        # Bruno prefers MEP and Ana oficial; recording the same payment from either side clears the same.
        _wire_waterfall(monkeypatch, DollarRate.blue)
        plans = []
        for viewer, seat in ((ANA, ANA_SEAT), (BRUNO, BRUNO_SEAT)):
            monkeypatch.setattr(group_settlement_service.group_service, "require_member", AsyncMock(return_value=(GROUP, seat)))
            plan = await group_settlement_service.preview_waterfall(
                AsyncMock(), GROUP_ID, viewer, from_member_id=ANA_SEAT.id, to_member_id=BRUNO_SEAT.id, date=DAY, amount=Decimal("40"), currency="USD"
            )
            plans.append([(bucket.currency, bucket.cost, bucket.amount) for bucket in plan.buckets])
        assert plans[0] == plans[1] == [("ARS", Decimal("20.00"), Decimal("30000"))]


class TestTheBalanceAtTodaysRateIsTheGroups:
    @pytest.mark.asyncio
    async def test_the_converted_balance_reads_the_group_rate_for_every_member(self, monkeypatch):
        # Ana's 10-dollar debt shown in pesos: 15,000 under a blue group, whatever Ana prefers.
        _wire_waterfall(monkeypatch, DollarRate.blue)
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, ANA, currency="ARS")
        usd = next(bucket for bucket in result.buckets if bucket.currency == "USD")
        assert usd.my_converted_balance == Decimal("-15000.00")


# --- Changing it takes every active member's agreement ---


class TestTheMembersAgree:
    @staticmethod
    def _wire(monkeypatch, seats: list[GroupMember], settings: GroupMoneySettings | None = None) -> tuple[GroupMoneySettings, AsyncMock]:
        settings = settings or GroupMoneySettings(group_id=GROUP_ID)
        by_user = {seat.user_id: seat for seat in seats if seat.user_id is not None}
        monkeypatch.setattr(
            group_money_service.group_service, "require_member", AsyncMock(side_effect=lambda _s, _g, user: (GROUP, by_user[user.id]))
        )
        monkeypatch.setattr(group_money_service.group_repository, "lock", AsyncMock())
        monkeypatch.setattr(group_money_service.group_repository, "list_members", AsyncMock(return_value=seats))
        monkeypatch.setattr(group_money_service.group_money_settings_repository, "get_by_group_id", AsyncMock(return_value=settings))
        monkeypatch.setattr(group_money_service.group_money_settings_repository, "save", AsyncMock())
        monkeypatch.setattr(group_money_service.group_repository, "get_by_id", AsyncMock(return_value=GROUP))
        # The announcements, read back through group_money_service.notification_service.
        monkeypatch.setattr(group_money_service.notification_service, "dispatch", AsyncMock())
        monkeypatch.setattr(group_money_service.notification_service, "dispatch_many", AsyncMock())
        audit = AsyncMock()
        monkeypatch.setattr(group_money_service.shared_audit_service, "record", audit)
        return (settings, audit)

    @staticmethod
    def _steps(audit: AsyncMock) -> list[tuple[str, dict]]:
        return [(call.kwargs["action"].value, call.kwargs["payload"]) for call in audit.await_args_list]

    @pytest.mark.asyncio
    async def test_the_only_active_member_changes_it_at_once(self, monkeypatch):
        # Name-only and departed seats are never waited for, so Ana is alone here.
        settings, audit = self._wire(monkeypatch, [ANA_SEAT, NAME_ONLY_SEAT, LEFT_SEAT])
        response = await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)
        assert (settings.dollar_rate, settings.dollar_rate_proposal) == (DollarRate.blue, None)
        assert response.dollar_rate == DollarRate.blue and response.dollar_rate_proposal is None
        assert self._steps(audit) == [("updated", {"variant": "dollar_rate", "from_rate": "mep", "to_rate": "blue"})]

    @pytest.mark.asyncio
    async def test_nothing_changes_until_every_active_member_has_agreed(self, monkeypatch):
        settings, audit = self._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT, NAME_ONLY_SEAT])

        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, BRUNO, dollar_rate=DollarRate.oficial)
        assert (settings.dollar_rate, settings.dollar_rate_proposal, settings.dollar_rate_agreed_by) == (DollarRate.mep, DollarRate.oficial, [101])

        await group_money_service.agree_dollar_rate(AsyncMock(), GROUP_ID, ANA)
        assert (settings.dollar_rate, settings.dollar_rate_agreed_by) == (DollarRate.mep, [101, 100])

        await group_money_service.agree_dollar_rate(AsyncMock(), GROUP_ID, CARLA)
        assert (settings.dollar_rate, settings.dollar_rate_proposal, settings.dollar_rate_agreed_by) == (DollarRate.oficial, None, [])
        assert [action for action, _ in self._steps(audit)] == ["updated", "confirmed", "confirmed", "updated"]
        assert self._steps(audit)[0][1] == {"variant": "dollar_rate_proposed", "from_rate": "mep", "to_rate": "oficial"}

    @pytest.mark.asyncio
    async def test_one_proposal_at_a_time_and_never_to_the_rate_in_force(self, monkeypatch):
        self._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT])
        with pytest.raises(GroupDollarRateUnchangedError):
            await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.mep)
        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)
        with pytest.raises(GroupDollarRateProposalPendingError):
            await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, BRUNO, dollar_rate=DollarRate.oficial)

    @pytest.mark.asyncio
    async def test_agreeing_twice_is_refused_and_agreeing_to_nothing_is_not_found(self, monkeypatch):
        self._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT])
        with pytest.raises(NotFoundError):
            await group_money_service.agree_dollar_rate(AsyncMock(), GROUP_ID, BRUNO)
        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)
        with pytest.raises(GroupDollarRateAlreadyAgreedError):
            await group_money_service.agree_dollar_rate(AsyncMock(), GROUP_ID, ANA)

    @pytest.mark.asyncio
    async def test_only_the_proposer_withdraws_and_withdrawing_changes_nothing(self, monkeypatch):
        settings, audit = self._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT])
        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)
        with pytest.raises(GroupDollarRateNotYoursError):
            await group_money_service.withdraw_dollar_rate(AsyncMock(), GROUP_ID, BRUNO)
        await group_money_service.withdraw_dollar_rate(AsyncMock(), GROUP_ID, ANA)
        assert (settings.dollar_rate, settings.dollar_rate_proposal, settings.dollar_rate_proposed_by, settings.dollar_rate_agreed_by) == (
            DollarRate.mep,
            None,
            None,
            [],
        )
        assert self._steps(audit)[-1] == ("updated", {"variant": "dollar_rate_withdrawn", "from_rate": "mep", "to_rate": "blue"})

    @pytest.mark.asyncio
    async def test_a_proposal_whose_proposer_left_can_be_withdrawn_by_a_member_it_waits_for(self, monkeypatch):
        pending = GroupMoneySettings(
            group_id=GROUP_ID, dollar_rate_proposal=DollarRate.blue, dollar_rate_proposed_by=LEFT_SEAT.id, dollar_rate_agreed_by=[LEFT_SEAT.id]
        )
        settings, _ = self._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, LEFT_SEAT], pending)
        await group_money_service.withdraw_dollar_rate(AsyncMock(), GROUP_ID, BRUNO)
        assert settings.dollar_rate_proposal is None

    @pytest.mark.asyncio
    async def test_the_response_says_who_it_waits_on_and_what_each_reader_may_do(self, monkeypatch):
        self._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT, NAME_ONLY_SEAT])
        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)

        mine = await group_money_service.get_settings(AsyncMock(), GROUP_ID, ANA)
        assert mine.can_change_dollar_rate is False
        assert (mine.dollar_rate_proposal.proposed_by, mine.dollar_rate_proposal.waiting_on) == ("Ana", ["Bruno", "Carla"])
        assert (mine.dollar_rate_proposal.can_agree, mine.dollar_rate_proposal.can_withdraw) == (False, True)

        theirs = await group_money_service.get_settings(AsyncMock(), GROUP_ID, BRUNO)
        assert (theirs.dollar_rate_proposal.can_agree, theirs.dollar_rate_proposal.can_withdraw) == (True, False)


class TestTheMembersAreTold:
    # Each step reaches the members it concerns, through `settle_rate_changed`, the way a pot's owners
    # hear about a change of a pot's rate.

    @staticmethod
    def _sent() -> tuple[AsyncMock, AsyncMock]:
        return (group_money_service.notification_service.dispatch, group_money_service.notification_service.dispatch_many)

    @staticmethod
    def _fan_out(dispatch_many: AsyncMock) -> dict[str, list[int]]:
        return {item.payload["variant"]: item.user_ids for item in dispatch_many.await_args.args[1]}

    @pytest.mark.asyncio
    async def test_a_proposal_asks_every_other_member_and_its_application_tells_them(self, monkeypatch):
        TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT, NAME_ONLY_SEAT])
        dispatch, dispatch_many = self._sent()

        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)
        event, recipients, payload = dispatch.await_args.args
        assert event == NotificationEvent.settle_rate_changed
        assert recipients == [BRUNO.id, CARLA.id]
        assert payload == {"group_id": GROUP_ID, "group": "Casa", "actor": "Ana", "variant": "dollar_rate_proposed_to_you"}

        await group_money_service.agree_dollar_rate(AsyncMock(), GROUP_ID, BRUNO)
        dispatch_many.assert_not_awaited()
        await group_money_service.agree_dollar_rate(AsyncMock(), GROUP_ID, CARLA)
        # The proposer reads that everyone agreed to theirs, the others that the group settles at it now;
        # Carla gave the last agreement, so she is not told about her own act.
        assert dispatch_many.await_args.args[0] == NotificationEvent.settle_rate_changed
        assert self._fan_out(dispatch_many) == {"dollar_rate_applied_from_you": [ANA.id], "dollar_rate_applied_to_you": [BRUNO.id]}
        assert {item.payload["actor"] for item in dispatch_many.await_args.args[1]} == {"Ana"}

    @pytest.mark.asyncio
    async def test_a_withdrawal_tells_the_members_who_were_asked(self, monkeypatch):
        TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT])
        dispatch, _ = self._sent()
        await group_money_service.propose_dollar_rate(AsyncMock(), GROUP_ID, ANA, dollar_rate=DollarRate.blue)
        await group_money_service.withdraw_dollar_rate(AsyncMock(), GROUP_ID, ANA)
        _, recipients, payload = dispatch.await_args.args
        assert recipients == [BRUNO.id, CARLA.id]
        assert payload["variant"] == "dollar_rate_withdrawn_to_you"

    @pytest.mark.asyncio
    async def test_a_change_the_last_holdout_leaving_applied_is_announced_to_who_is_left(self, monkeypatch):
        pending = GroupMoneySettings(
            group_id=GROUP_ID, dollar_rate_proposal=DollarRate.blue, dollar_rate_proposed_by=ANA_SEAT.id, dollar_rate_agreed_by=[ANA_SEAT.id, 102]
        )
        TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT], pending)
        _, dispatch_many = self._sent()
        applied = await group_money_service.settle_dollar_rate_proposal(AsyncMock(), GROUP_ID, BRUNO, leaving=frozenset({BRUNO_SEAT.id}))
        await group_money_service.announce_dollar_rate_applied(applied)
        assert self._fan_out(dispatch_many) == {"dollar_rate_applied_from_you": [ANA.id], "dollar_rate_applied_to_you": [CARLA.id]}


class TestTheRosterMovesWhileAChangeWaits:
    @pytest.mark.asyncio
    async def test_it_applies_once_the_last_member_it_waited_for_leaves(self, monkeypatch):
        pending = GroupMoneySettings(
            group_id=GROUP_ID, dollar_rate_proposal=DollarRate.blue, dollar_rate_proposed_by=ANA_SEAT.id, dollar_rate_agreed_by=[ANA_SEAT.id]
        )
        settings, _ = TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT], pending)
        await group_money_service.settle_dollar_rate_proposal(AsyncMock(), GROUP_ID, BRUNO, leaving=frozenset({BRUNO_SEAT.id}))
        assert (settings.dollar_rate, settings.dollar_rate_proposal) == (DollarRate.blue, None)

    @pytest.mark.asyncio
    async def test_it_keeps_waiting_while_somebody_it_waits_for_is_still_here(self, monkeypatch):
        pending = GroupMoneySettings(
            group_id=GROUP_ID, dollar_rate_proposal=DollarRate.blue, dollar_rate_proposed_by=ANA_SEAT.id, dollar_rate_agreed_by=[ANA_SEAT.id]
        )
        settings, audit = TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT], pending)
        await group_money_service.settle_dollar_rate_proposal(AsyncMock(), GROUP_ID, BRUNO, leaving=frozenset({BRUNO_SEAT.id}))
        assert (settings.dollar_rate, settings.dollar_rate_proposal) == (DollarRate.mep, DollarRate.blue)
        audit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_seat_that_lost_its_account_stops_being_waited_for(self, monkeypatch):
        # Account deletion: the seat stays active but reads as a placeholder once the user row is gone.
        pending = GroupMoneySettings(
            group_id=GROUP_ID, dollar_rate_proposal=DollarRate.blue, dollar_rate_proposed_by=ANA_SEAT.id, dollar_rate_agreed_by=[ANA_SEAT.id]
        )
        deleted = _seat(BRUNO_SEAT.id, None, "Bruno")
        settings, _ = TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, deleted], pending)
        await group_money_service.settle_dollar_rate_proposal(AsyncMock(), GROUP_ID, None)
        assert settings.dollar_rate == DollarRate.blue

    @pytest.mark.asyncio
    async def test_a_member_who_joins_while_it_waits_is_waited_for_too(self, monkeypatch):
        pending = GroupMoneySettings(
            group_id=GROUP_ID, dollar_rate_proposal=DollarRate.blue, dollar_rate_proposed_by=ANA_SEAT.id, dollar_rate_agreed_by=[ANA_SEAT.id, 101]
        )
        TestTheMembersAgree._wire(monkeypatch, [ANA_SEAT, BRUNO_SEAT, CARLA_SEAT], pending)
        response = await group_money_service.get_settings(AsyncMock(), GROUP_ID, CARLA)
        assert response.dollar_rate_proposal.waiting_on == ["Carla"]
        assert response.dollar_rate_proposal.can_agree is True


class TestANewGroupPicksItsRate:
    @pytest.mark.asyncio
    async def test_the_rate_chosen_at_creation_is_the_one_seeded(self, monkeypatch):
        seed = AsyncMock()
        monkeypatch.setattr(group_money_service, "seed_settings", seed)
        monkeypatch.setattr(group_service.group_repository, "create", AsyncMock(side_effect=lambda _s, g: g.model_copy(update={"id": GROUP_ID})))
        monkeypatch.setattr(group_service.group_repository, "create_member", AsyncMock(side_effect=lambda _s, m: m.model_copy(update={"id": 1})))
        monkeypatch.setattr(group_service.shared_audit_service, "record", AsyncMock())
        from app.models.group import GroupKind as Kind

        await group_service.create_group(AsyncMock(), ANA, name="Casa", kind=Kind.household, dollar_rate=DollarRate.blue)
        assert seed.await_args.kwargs["dollar_rate"] == DollarRate.blue


# --- A pot owner's share cannot be left behind ---


def _opening(pot_id: int, member_id: int, units: str) -> PotOwnershipEvent:
    return PotOwnershipEvent(
        id=pot_id * 1000 + member_id,
        pot_id=pot_id,
        type=OwnershipEventType.opening,
        date=date(2026, 1, 1),
        member_id=member_id,
        units=Decimal(units),
        unit_price=Decimal("1"),
    )


def _bought_out(pot_id: int, member_id: int, to_member_id: int, units: str) -> PotOwnershipEvent:
    return PotOwnershipEvent(
        id=pot_id * 1000 + member_id + 500,
        pot_id=pot_id,
        type=OwnershipEventType.reagreement,
        date=date(2026, 2, 1),
        member_id=member_id,
        counterparty_member_id=to_member_id,
        units=-Decimal(units),
        unit_price=Decimal("1"),
    )


class TestAPotOwnerCannotGoInactive:
    @staticmethod
    def _wire(monkeypatch, events_by_pot: dict[int, list[PotOwnershipEvent]]) -> None:
        monkeypatch.setattr(pot_service.pot_repository, "list_ids_by_groups", AsyncMock(return_value=sorted(events_by_pot)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pots", AsyncMock(return_value=events_by_pot))

    @pytest.mark.asyncio
    async def test_a_seat_holding_units_in_any_pot_is_refused(self, monkeypatch):
        self._wire(monkeypatch, {5: [_opening(5, 100, "100")], 6: [_opening(6, 100, "40"), _opening(6, 101, "60")]})
        with pytest.raises(GroupMemberOwnsPotError):
            await pot_service.ensure_no_units(AsyncMock(), [BRUNO_SEAT])

    @pytest.mark.asyncio
    async def test_a_share_that_was_bought_out_no_longer_counts(self, monkeypatch):
        self._wire(monkeypatch, {6: [_opening(6, 100, "40"), _opening(6, 101, "60"), _bought_out(6, 101, 100, "60")]})
        await pot_service.ensure_no_units(AsyncMock(), [BRUNO_SEAT])

    @pytest.mark.asyncio
    async def test_somebody_elses_units_are_not_this_seats(self, monkeypatch):
        self._wire(monkeypatch, {5: [_opening(5, 100, "100")]})
        await pot_service.ensure_no_units(AsyncMock(), [BRUNO_SEAT])

    @pytest.mark.asyncio
    async def test_removing_or_leaving_asks_on_the_privileged_session_before_the_seat_goes(self, monkeypatch):
        # The admin removing Bruno may not see every pot Bruno owns part of, so the guard is handed the
        # privileged session — and nothing is written once it refuses.
        admin_session = AsyncMock()
        guard = AsyncMock(side_effect=GroupMemberOwnsPotError())
        monkeypatch.setattr(pot_service, "ensure_no_units", guard)
        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, ANA_SEAT)))
        monkeypatch.setattr(group_service.group_repository, "get_member", AsyncMock(return_value=BRUNO_SEAT.model_copy()))
        monkeypatch.setattr(group_service.group_repository, "lock", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "ensure_no_outstanding_balance", AsyncMock())
        save_member = AsyncMock()
        monkeypatch.setattr(group_service.group_repository, "save_member", save_member)

        with pytest.raises(GroupMemberOwnsPotError):
            await group_service.remove_member(AsyncMock(), admin_session, GROUP_ID, BRUNO_SEAT.id, ANA)

        assert guard.await_args.args[0] is admin_session
        assert [seat.id for seat in guard.await_args.args[1]] == [BRUNO_SEAT.id]
        save_member.assert_not_awaited()
