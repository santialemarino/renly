# The ownership ledger's guards: what may be recorded, at what price, and by whom.
#
# The unit math itself is tested in test_pot_unit_accounting.py against hand-computed values. This
# file tests the rules AROUND it — the ones that decide whether an event is written at all.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    NotFoundError,
    PotAlreadyOpenedError,
    PotInsufficientUnitsError,
    PotNotOpenedError,
    PotPercentagesError,
    PotReagreementSameMemberError,
    PotUnsupportedMovementError,
    PotValuationRequiredError,
    PotWriteRequiredError,
)
from app.domain.errors import AccountCurrencyMismatchError
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent
from app.models.user import User
from app.services import pot_ownership_service as svc

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
POT = Pot(id=5, group_id=10, base_currency="USD", is_default=True)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
OTHER_SEAT = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member)


def _event(**kwargs) -> PotOwnershipEvent:
    defaults = dict(
        id=1,
        pot_id=5,
        type=OwnershipEventType.opening,
        date=date(2026, 1, 1),
        member_id=100,
        units=Decimal("100"),
        unit_price=Decimal("1"),
    )
    return PotOwnershipEvent(**{**defaults, **kwargs})


def _account(id: int, *, user_id: int | None = 1, pot_id: int | None = None, currency: str = "USD") -> Account:
    return Account(id=id, user_id=user_id, pot_id=pot_id, name="A", type=AccountType.bank, currency=currency, opening_date=date(2026, 1, 1))


# Wires the shared happy-path collaborators: write access granted, seats resolvable, one member
# holding 100 units, and a NAV of 110 so the unit price is a clean 1.10.
def _arrange(monkeypatch, *, events=None, nav=Decimal("110")):
    monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
    monkeypatch.setattr(svc.group_repository, "get_member", AsyncMock(side_effect=lambda _s, _g, mid: {100: SEAT, 101: OTHER_SEAT}.get(mid)))
    # record_opening resolves the whole roster in one query rather than a seat at a time.
    monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[SEAT, OTHER_SEAT]))
    monkeypatch.setattr(svc.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=events if events is not None else [_event()]))
    monkeypatch.setattr(svc.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=AsyncMock()))
    monkeypatch.setattr(svc.pot_service, "get_nav", AsyncMock(return_value=nav))

    # The real repository flushes to get an id; the stub does the same, or every response build
    # would fail validation for a reason that has nothing to do with what is being tested.
    def _persist(_session, event):
        event.id = event.id or 900
        return event

    created = AsyncMock(side_effect=_persist)
    monkeypatch.setattr(svc.pot_ownership_repository, "create", created)

    # The opening writes one row per owner in a single batch; every other event writes one row.
    def _persist_many(_session, events):
        for n, event in enumerate(events, start=900):
            event.id = event.id or n
        return events

    monkeypatch.setattr(svc.pot_ownership_repository, "create_many", AsyncMock(side_effect=_persist_many))
    return created


class TestOpening:
    @pytest.mark.asyncio
    async def test_percentages_that_do_not_total_100_are_refused(self, monkeypatch):
        created = _arrange(monkeypatch, events=[])
        with pytest.raises(PotPercentagesError) as excinfo:
            await svc.record_opening(
                AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("90"), 101: Decimal("5")}
            )
        assert excinfo.value.extra == {"total": "95"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_second_baseline_is_refused(self, monkeypatch):
        # The baseline IS the division every later percentage derives from, so a second one would
        # silently rewrite what everyone agreed to.
        created = _arrange(monkeypatch, events=[_event()])
        with pytest.raises(PotAlreadyOpenedError):
            await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("100")})
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_seat_from_another_group_cannot_be_given_units(self, monkeypatch):
        created = _arrange(monkeypatch, events=[])
        with pytest.raises(NotFoundError):
            await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={999: Decimal("100")})
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_roster_is_loaded_ONCE_however_many_owners_the_opening_names(self, monkeypatch):
        # An opening names every owner, so validating a seat at a time is an N+1 that grows with the
        # group. Asserted by counting the calls, because the per-seat version returns the same rows
        # and produces an identical result — only the query count differs.
        _arrange(monkeypatch, events=[])
        roster = AsyncMock(return_value=[SEAT, OTHER_SEAT])
        per_seat = AsyncMock(side_effect=lambda _s, _g, mid: {100: SEAT, 101: OTHER_SEAT}.get(mid))
        monkeypatch.setattr(svc.group_repository, "list_members", roster)
        monkeypatch.setattr(svc.group_repository, "get_member", per_seat)
        await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("60"), 101: Decimal("40")})
        assert roster.await_count == 1
        per_seat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_deactivated_seat_cannot_be_given_units(self, monkeypatch):
        # A removed member's seat survives so the rows referencing it keep a real counterparty — but
        # it is not an owner, and issuing units to one would put a share of the pot somewhere nobody
        # can reach or settle.
        _arrange(monkeypatch, events=[])
        removed = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member, is_active=False)
        monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[SEAT, removed]))
        with pytest.raises(NotFoundError):
            await svc.record_opening(
                AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("60"), 101: Decimal("40")}
            )
        svc.pot_ownership_repository.create_many.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_units_are_issued_at_a_nominal_one_so_they_read_as_percentages(self, monkeypatch):
        _arrange(monkeypatch, events=[])
        await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("90"), 101: Decimal("10")})
        written = svc.pot_ownership_repository.create_many.await_args.args[1]
        assert [(e.member_id, e.units, e.unit_price) for e in written] == [
            (100, Decimal("90.000000"), Decimal("1")),
            (101, Decimal("10.000000"), Decimal("1")),
        ]
        assert all(e.type == OwnershipEventType.opening for e in written)

    @pytest.mark.asyncio
    async def test_write_access_is_required(self, monkeypatch):
        monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(side_effect=PotWriteRequiredError()))
        with pytest.raises(PotWriteRequiredError):
            await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("100")})


class TestMovements:
    @pytest.mark.asyncio
    async def test_a_contribution_issues_units_at_the_dates_price(self, monkeypatch):
        # NAV 110 over 100 units = 1.10; 5 / 1.10 = 4.545455 (six places, half-up).
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7)))
        await svc.record_movement(
            AsyncMock(), 5, USER, type=OwnershipEventType.contribution, date=date(2026, 6, 1), member_id=100, amount=Decimal("5")
        )
        written = created.await_args.args[1]
        assert (written.units, written.unit_price, written.base_amount) == (Decimal("4.545455"), Decimal("1.100000"), Decimal("5"))

    @pytest.mark.asyncio
    async def test_a_withdrawal_redeems_units_as_a_negative(self, monkeypatch):
        created = _arrange(monkeypatch)
        await svc.record_movement(
            AsyncMock(), 5, USER, type=OwnershipEventType.withdrawal, date=date(2026, 6, 1), member_id=100, amount=Decimal("11")
        )
        assert created.await_args.args[1].units == Decimal("-10.000000")

    @pytest.mark.asyncio
    async def test_a_withdrawal_larger_than_the_holding_is_refused(self, monkeypatch):
        # 100 units at 1.10 is worth 110; asking for 220 would leave a negative share of the pot.
        created = _arrange(monkeypatch)
        with pytest.raises(PotInsufficientUnitsError) as excinfo:
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.withdrawal, date=date(2026, 6, 1), member_id=100, amount=Decimal("220")
            )
        assert excinfo.value.extra == {"held": "100", "requested": "200.000000"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_movement_against_a_pot_with_no_baseline_is_refused(self, monkeypatch):
        created = _arrange(monkeypatch, events=[])
        with pytest.raises(PotNotOpenedError):
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.contribution, date=date(2026, 6, 1), member_id=100, amount=Decimal("5")
            )
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_movement_on_a_date_with_no_valuation_is_refused_not_guessed(self, monkeypatch):
        # Same posture as reconciliation refusing to invent a figure.
        created = _arrange(monkeypatch, nav=None)
        with pytest.raises(PotValuationRequiredError) as excinfo:
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.contribution, date=date(2026, 6, 1), member_id=100, amount=Decimal("5")
            )
        assert excinfo.value.extra == {"as_of_date": "2026-06-01"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_pot_valued_at_zero_has_no_price_to_issue_against(self, monkeypatch):
        created = _arrange(monkeypatch, nav=Decimal("0"))
        with pytest.raises(PotValuationRequiredError):
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.contribution, date=date(2026, 6, 1), member_id=100, amount=Decimal("5")
            )
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_private_leg_must_belong_to_the_caller(self, monkeypatch):
        # Otherwise one member could move money out of another's account by naming its id.
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7, user_id=999)))
        with pytest.raises(NotFoundError):
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.contribution,
                date=date(2026, 6, 1),
                member_id=100,
                amount=Decimal("5"),
                from_account_id=7,
            )
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_pot_leg_must_belong_to_this_pot(self, monkeypatch):
        # Otherwise a contribution would credit a different pot entirely.
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7, user_id=None, pot_id=99)))
        with pytest.raises(NotFoundError):
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.contribution,
                date=date(2026, 6, 1),
                member_id=100,
                amount=Decimal("5"),
                to_account_id=7,
            )
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_pot_leg_must_be_in_the_pots_base_currency(self, monkeypatch):
        # What makes base_amount unambiguous: otherwise the credited figure would be in a third
        # currency and neither stored amount would describe the account it landed in.
        created = _arrange(monkeypatch)
        shared_ars = _account(7, user_id=None, pot_id=5, currency="ARS")
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=shared_ars))
        with pytest.raises(AccountCurrencyMismatchError):
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.contribution,
                date=date(2026, 6, 1),
                member_id=100,
                amount=Decimal("5"),
                to_account_id=7,
            )
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_cross_currency_move_stores_both_amounts_and_no_rate(self, monkeypatch):
        # Merged constraint (f): record what left and what was credited, never a derived rate.
        created = _arrange(monkeypatch)
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.contribution,
            date=date(2026, 6, 1),
            member_id=100,
            amount=Decimal("5000"),
            amount_currency="ARS",
            base_amount=Decimal("5"),
        )
        written = created.await_args.args[1]
        assert (written.amount, written.amount_currency, written.base_amount) == (Decimal("5000"), "ARS", Decimal("5"))
        # Units follow the BASE amount, not the source one — 5 / 1.10, not 5000 / 1.10.
        assert written.units == Decimal("4.545455")

    @pytest.mark.asyncio
    async def test_a_same_currency_move_stores_no_redundant_currency(self, monkeypatch):
        created = _arrange(monkeypatch)
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.contribution,
            date=date(2026, 6, 1),
            member_id=100,
            amount=Decimal("5"),
            amount_currency="USD",
        )
        assert created.await_args.args[1].amount_currency is None

    @pytest.mark.asyncio
    async def test_a_cross_currency_move_without_a_base_amount_is_refused(self, monkeypatch):
        created = _arrange(monkeypatch)
        with pytest.raises(AccountCurrencyMismatchError):
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.contribution,
                date=date(2026, 6, 1),
                member_id=100,
                amount=Decimal("5000"),
                amount_currency="ARS",
            )
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_opening_cannot_be_recorded_through_the_movement_endpoint(self, monkeypatch):
        created = _arrange(monkeypatch)
        with pytest.raises(PotUnsupportedMovementError):
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.opening, date=date(2026, 6, 1), member_id=100, amount=Decimal("5")
            )
        created.assert_not_awaited()


class TestReagreement:
    @pytest.mark.asyncio
    async def test_units_move_between_members_and_carry_no_money(self, monkeypatch):
        created = _arrange(monkeypatch)
        await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=Decimal("20"))
        written = created.await_args.args[1]
        # 20% of 100 units outstanding, signed against the GIVER so the replay needs no per-type rule.
        assert (written.member_id, written.counterparty_member_id, written.units) == (100, 101, Decimal("-20.000000"))
        assert (written.amount, written.base_amount, written.from_account_id, written.to_account_id) == (None, None, None, None)

    @pytest.mark.asyncio
    async def test_moving_more_than_the_giver_holds_is_refused(self, monkeypatch):
        created = _arrange(monkeypatch, events=[_event(member_id=100, units=Decimal("10")), _event(id=2, member_id=101, units=Decimal("90"))])
        with pytest.raises(PotInsufficientUnitsError):
            await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=Decimal("50"))
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_one_member_on_both_sides_is_refused(self, monkeypatch):
        created = _arrange(monkeypatch)
        with pytest.raises(PotReagreementSameMemberError):
            await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=100, percentage=Decimal("10"))
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_write_access_is_required(self, monkeypatch):
        monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(side_effect=PotWriteRequiredError()))
        with pytest.raises(PotWriteRequiredError):
            await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=Decimal("10"))


class TestReading:
    @pytest.mark.asyncio
    async def test_the_ledger_is_visible_to_anyone_who_may_see_the_pot(self, monkeypatch):
        # V5: a member holding 0% still sees every movement. list_events gates on VISIBILITY, never on
        # write access and never on holding units.
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, OTHER_SEAT, None)))
        monkeypatch.setattr(svc.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[_event()]))
        monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[SEAT, OTHER_SEAT]))
        events = await svc.list_events(AsyncMock(), 5, USER)
        assert [(e.member_id, e.member_name) for e in events] == [(100, "Santi")]

    @pytest.mark.asyncio
    async def test_deleting_an_event_requires_write_access(self, monkeypatch):
        monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(side_effect=PotWriteRequiredError()))
        with pytest.raises(PotWriteRequiredError):
            await svc.delete_event(AsyncMock(), 5, 1, USER)

    @pytest.mark.asyncio
    async def test_an_event_is_looked_up_scoped_to_its_own_pot(self, monkeypatch):
        # Asserted on the ARGUMENTS the service passed, not on what the stub handed back. A stub
        # returning None passes whatever the service asks for, so "it raised NotFoundError" would be
        # true even if the pot id were never part of the lookup at all — which is exactly how an event
        # id from another pot would become reachable by guessing.
        monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
        get_by_id = AsyncMock(return_value=None)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", get_by_id)
        delete = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete)
        with pytest.raises(NotFoundError):
            await svc.delete_event(AsyncMock(), 5, 999, USER)
        assert get_by_id.await_args.args[1:] == (POT.id, 999)
        delete.assert_not_awaited()
