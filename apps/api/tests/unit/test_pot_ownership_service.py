# The ownership ledger's guards: what may be recorded, at what price, and by whom.
#
# The unit math itself is tested in test_pot_unit_accounting.py against hand-computed values. This
# file tests the rules AROUND it — the ones that decide whether an event is written at all.

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    NotFoundError,
    PotAlreadyOpenedError,
    PotBaseAmountRequiredError,
    PotEventNotConfirmableError,
    PotInsufficientUnitsError,
    PotMovementAccountInactiveError,
    PotMovementBeforeAccountOpenedError,
    PotNotOpenedError,
    PotPercentagesError,
    PotReagreementConfirmedError,
    PotReagreementNotYoursError,
    PotReagreementSameMemberError,
    PotUnsupportedMovementError,
    PotValuationRequiredError,
    PotWriteRequiredError,
)
from app.domain.errors import AccountCurrencyMismatchError
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.investment import Investment, InvestmentCategory
from app.models.notification import NotificationEvent
from app.models.pot import OwnershipEventType, Pot, PotMemberPermission, PotOwnershipEvent
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User
from app.schemas.pot import PotHoldingResponse
from app.services import pot_ownership_service as svc

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
POT = Pot(id=5, group_id=10, base_currency="USD", is_default=True)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
OTHER_SEAT = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member)
WRITER = PotMemberPermission(pot_id=5, member_id=100, can_view=True, can_write=True)
READER = PotMemberPermission(pot_id=5, member_id=100, can_view=True, can_write=False)


# One shared dispatch mock, reset per arrangement, so TestWhatIsAnnounced can read it without every
# other test having to thread a second return value through _arrange.
_DISPATCHED = AsyncMock()


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


def _account(
    id: int,
    *,
    user_id: int | None = 1,
    pot_id: int | None = None,
    currency: str = "USD",
    opening_date: date = date(2026, 1, 1),
) -> Account:
    return Account(id=id, user_id=user_id, pot_id=pot_id, name="A", type=AccountType.bank, currency=currency, opening_date=opening_date)


# Wires the shared happy-path collaborators: write access granted, seats resolvable, one member
# holding 100 units, and a NAV of 110 so the unit price is a clean 1.10.
def _arrange(monkeypatch, *, events=None, nav=Decimal("110")):
    monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
    # delete_event asks the WIDER question and resolves the write check itself, because one act there is
    # not gated on write access at all.
    monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, WRITER)))
    monkeypatch.setattr(svc.pot_repository, "lock", AsyncMock())
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

    # The notification fan-out every write ends with. Stubbed at the two seams a mocked session cannot
    # serve: the pot's audience (a roster + permissions read) and the group's name. `dispatch` itself is
    # captured rather than silenced, so the tests below can assert WHAT was announced — see
    # TestNotifications.
    monkeypatch.setattr(svc.pot_service, "list_notifiable_user_ids", AsyncMock(return_value=[OTHER_SEAT.user_id]))
    monkeypatch.setattr(svc.group_repository, "get_by_id", AsyncMock(return_value=GROUP))
    monkeypatch.setattr(svc.notification_service, "dispatch", _DISPATCHED)
    _DISPATCHED.reset_mock()
    return created


class TestWhatIsAnnounced:
    # Addressed by the POT's visibility rather than the group's, because an 'owners' pot must not
    # announce itself to a member who cannot see it — a notification that discloses what the policy
    # hides is the one failure this whole audience rule exists to prevent.

    @pytest.mark.asyncio
    async def test_an_opening_says_the_pot_has_been_divided(self, monkeypatch):
        _arrange(monkeypatch, events=[])
        await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("100")})
        event, recipients, payload = _DISPATCHED.await_args.args
        assert event == NotificationEvent.ownership_changed
        assert recipients == [OTHER_SEAT.user_id]
        assert payload == {"group_id": 10, "group": "Casa", "pot_id": 5, "pot": None, "variant": "opening", "actor": SEAT.display_name}

    @pytest.mark.asyncio
    async def test_a_contribution_names_whose_units_moved_and_what_the_POT_took_in(self, monkeypatch):
        # Not the source amount: a cross-currency movement's two figures are different numbers in
        # different currencies, and what changed for every reader is what the pot was credited.
        _arrange(monkeypatch)
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.contribution,
            date=date(2026, 2, 1),
            member_id=101,
            amount=Decimal("1100"),
            amount_currency="ARS",
            base_amount=Decimal("11"),
        )
        event, _recipients, payload = _DISPATCHED.await_args.args
        assert event == NotificationEvent.pot_movement
        assert payload["variant"] == "contribution"
        assert payload["member"] == OTHER_SEAT.display_name
        assert (payload["amount"], payload["currency"]) == ("11", "USD")

    @pytest.mark.asyncio
    async def test_a_withdrawal_reads_as_money_leaving(self, monkeypatch):
        _arrange(monkeypatch)
        await svc.record_movement(
            AsyncMock(), 5, USER, type=OwnershipEventType.withdrawal, date=date(2026, 2, 1), member_id=100, amount=Decimal("11")
        )
        assert _DISPATCHED.await_args.args[2]["variant"] == "withdrawal"

    @pytest.mark.asyncio
    async def test_a_re_agreement_names_both_sides_and_carries_no_figure(self, monkeypatch):
        # What moved is a number of UNITS, which no surface shows a person (U2: percentages in,
        # percentages out) — and the percentage is not on the event, so any figure here would be a
        # second answer to a question the pot page already answers.
        _arrange(monkeypatch)
        await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 2, 1), from_member_id=100, to_member_id=101, percentage=Decimal("10"))
        event, _recipients, payload = _DISPATCHED.await_args.args
        assert event == NotificationEvent.ownership_changed
        assert payload["variant"] == "reagreement"
        assert (payload["from_member"], payload["to_member"]) == (SEAT.display_name, OTHER_SEAT.display_name)
        assert "amount" not in payload

    @pytest.mark.asyncio
    async def test_DELETING_an_event_announces_it_like_any_other_ownership_change(self, monkeypatch):
        """Every deletion, not only the counterparty's, and that widening is the point.

        Until now a pot's writer could delete an opening or a contribution and every percentage on the
        page would change with nobody told. Undoing an act is as much a change to what people own as
        making it was, and whoever recorded the original has to learn it was undone or they go on
        believing a split that no longer holds.
        """
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=_event(type=OwnershipEventType.contribution)))
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", AsyncMock())
        await svc.delete_event(AsyncMock(), 5, 1, USER)
        event, recipients, payload = _DISPATCHED.await_args.args
        # ownership_changed with a variant rather than an event of its own, so somebody who has switched
        # pot-ownership news off stays switched off for the undo too.
        assert event == NotificationEvent.ownership_changed
        assert recipients == [OTHER_SEAT.user_id]
        assert payload["variant"] == "deleted"
        assert payload["actor"] == SEAT.display_name
        # Which KIND of entry went is deliberately absent: the four event types are named on the web and
        # nowhere else, so an email would need a second vocabulary of them in both locales. The audit
        # entry beside this one records the type, for the surface that can read it.
        assert "entry" not in payload


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
    async def test_a_baseline_is_refused_under_a_CONTRIBUTION_too_and_the_message_says_so(self, monkeypatch):
        """The rule is "the ledger is empty", not "no opening exists", and the difference is reachable:
        deleting a baseline keeps the movements that followed it, so a pot can sit here with a
        contribution and no opening at all. A baseline retro-fitted beneath movements already priced at
        other rates would issue units at a nominal 1.00 alongside them, so the units would mean two
        different things.

        The message is asserted because the old one said "already has an opening baseline" — which in
        exactly this state is untrue, and the only test covering the guard used an opening event.
        """
        created = _arrange(monkeypatch, events=[_event(type=OwnershipEventType.contribution, units=Decimal("100"))])
        with pytest.raises(PotAlreadyOpenedError) as excinfo:
            await svc.record_opening(AsyncMock(), 5, USER, date=date(2026, 1, 1), value=Decimal("100"), shares={100: Decimal("100")})
        assert "opening baseline" not in str(excinfo.value)
        assert "ownership history" in str(excinfo.value)
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
        with pytest.raises(AccountCurrencyMismatchError) as excinfo:
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
        # The message must name the account's REAL currency. Reversing the two arguments reports the
        # pot's base currency AS the account's, which states something untrue about the very account
        # the caller named — and reads as though ARS were the acceptable one.
        assert excinfo.value.extra == {"entry_currency": "USD", "account_currency": "ARS"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_private_leg_must_be_in_the_movements_own_currency(self, monkeypatch):
        # Merged constraint (a) — "entry currency = account currency" — on the leg that was missing it.
        # `amount` is what moves the PRIVATE account's balance (the repository's CASE reads that column
        # for a contribution's `from` leg), so a movement denominated in ARS against a USD account
        # subtracts an ARS figure from a USD balance. Nothing else in the system notices.
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7, currency="USD")))
        with pytest.raises(AccountCurrencyMismatchError) as excinfo:
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
                from_account_id=7,
            )
        assert excinfo.value.extra == {"entry_currency": "ARS", "account_currency": "USD"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_same_currency_private_leg_is_accepted(self, monkeypatch):
        # The positive control for the guard above: a check comparing the wrong pair of currencies
        # would refuse this too, and a test that only asserted the refusal would not notice.
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7, currency="USD")))
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
        assert created.await_args.args[1].from_account_id == 7

    @pytest.mark.asyncio
    async def test_the_pot_leg_cannot_be_an_ARCHIVED_account(self, monkeypatch):
        # Both NAV queries filter on is_active and the balance union does not, so crediting an archived
        # pot account moves that account's balance and leaves the pot's value where it was. Units get
        # issued against a NAV that never rises — every other owner diluted for nothing, from a
        # movement that looks completely ordinary.
        created = _arrange(monkeypatch)
        archived = _account(7, user_id=None, pot_id=5)
        archived.is_active = False
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=archived))
        with pytest.raises(PotMovementAccountInactiveError) as excinfo:
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
        assert excinfo.value.extra == {"account_id": 7}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_archived_PRIVATE_leg_is_still_allowed(self, monkeypatch):
        # The counterweight, and the reason the guard is on one leg only: a private account's balance
        # IS moved by the union whether it is archived or not, so nothing is issued against nothing.
        # Transfers take the same position — the API allows it and the pickers leave it out.
        created = _arrange(monkeypatch)
        archived = _account(7)
        archived.is_active = False
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=archived))
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
        created.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_movement_dated_before_its_private_account_opened_is_refused(self, monkeypatch):
        # The balance union bounds each leg by its OWN account's opening_date, so an earlier movement
        # issues units while the account it moved the money through never changes — value appearing in
        # the pot from nowhere. The same failure transfers refuse, and worse here because of the units.
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7, opening_date=date(2026, 5, 1))))
        with pytest.raises(PotMovementBeforeAccountOpenedError) as excinfo:
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.contribution,
                date=date(2026, 4, 30),
                member_id=100,
                amount=Decimal("5"),
                from_account_id=7,
            )
        assert excinfo.value.extra == {"opening_date": "2026-05-01"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_movement_ON_the_opening_date_is_allowed(self, monkeypatch):
        # The boundary is `date < opening`, not `<=`: opening_balance IS the balance at that date, and
        # the sum's own bound is `>=`, so a movement dated exactly then is counted.
        created = _arrange(monkeypatch)
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(7, opening_date=date(2026, 5, 1))))
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.contribution,
            date=date(2026, 5, 1),
            member_id=100,
            amount=Decimal("5"),
            from_account_id=7,
        )
        created.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_LATER_of_two_opening_dates_is_the_one_enforced(self, monkeypatch):
        # Each leg is bounded by its own account, so respecting only one of them still drops the other.
        created = _arrange(monkeypatch)
        accounts = {
            7: _account(7, opening_date=date(2026, 2, 1)),
            8: _account(8, user_id=None, pot_id=5, opening_date=date(2026, 7, 1)),
        }
        monkeypatch.setattr(svc.account_repository, "get_by_id_any_scope", AsyncMock(side_effect=lambda _s, aid: accounts[aid]))
        with pytest.raises(PotMovementBeforeAccountOpenedError) as excinfo:
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.contribution,
                date=date(2026, 6, 1),
                member_id=100,
                amount=Decimal("5"),
                from_account_id=7,
                to_account_id=8,
            )
        assert excinfo.value.extra == {"opening_date": "2026-07-01"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_movement_naming_no_account_has_no_opening_date_to_respect(self, monkeypatch):
        # Money can arrive from outside Renly entirely, so a movement with neither leg is legal and must
        # not be refused by a guard that has nothing to compare against.
        created = _arrange(monkeypatch)
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.contribution,
            date=date(1999, 1, 1),
            member_id=100,
            amount=Decimal("5"),
        )
        created.assert_awaited_once()

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
        # And refused as a MISSING FIELD, not as a currency mismatch: nothing here disagrees with
        # anything, the caller simply has not said what the pot was credited. Reporting a mismatch sent
        # them looking for an account whose currency was wrong, when the fix is to supply base_amount.
        created = _arrange(monkeypatch)
        with pytest.raises(PotBaseAmountRequiredError) as excinfo:
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
        assert excinfo.value.extra == {"amount_currency": "ARS", "base_currency": "USD"}
        assert not isinstance(excinfo.value, AccountCurrencyMismatchError)
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_opening_cannot_be_recorded_through_the_movement_endpoint(self, monkeypatch):
        created = _arrange(monkeypatch)
        with pytest.raises(PotUnsupportedMovementError):
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.opening, date=date(2026, 6, 1), member_id=100, amount=Decimal("5")
            )
        created.assert_not_awaited()


# Taking the WHOLE of a member's share out. The pair of tests below is the point: the same amount is
# refused without the flag and lands on the exact balance with it, so the flag is doing the work rather
# than decorating a case that already worked.
#
# The fixture is a three-unit pot worth 100, which makes the unit price 33.333333 — every figure a UI
# could reasonably prefill for "all of it" (the reported share value, units x price) is 66.67, and
# 66.67 / 33.333333 is 2.000100. That is not a contrived corner: over 224,200 plausible pots this
# division reproduced the holder's balance 4.6% of the time.
class TestHoldingContribution:
    # The fourth guided flow's write: a private holding moves into a DIVIDED pot and is paid for in
    # units, which is what makes it a contribution rather than the silent gift the plain move was
    # refused for. The valuation itself lives in pot_service and is stubbed here; what this class is
    # about is the arithmetic, the shape of the row, and the ORDER.

    @staticmethod
    def _valued(value="55", currency="USD", base_value="55"):
        return PotHoldingResponse(
            id=12,
            name="Fondo",
            currency=currency,
            value=Decimal(value),
            base_value=Decimal(base_value),
            is_active=True,
            valued_on=date(2026, 2, 1),
        )

    @staticmethod
    def _wire(monkeypatch, *, valued=None, holding=None):
        monkeypatch.setattr(
            svc.pot_service,
            "require_contributable_holding",
            AsyncMock(return_value=holding or Investment(id=12, user_id=1, name="Fondo", category=InvestmentCategory.fci, base_currency="USD")),
        )
        monkeypatch.setattr(svc.pot_service, "value_contributed_holding", AsyncMock(return_value=valued or TestHoldingContribution._valued()))
        attach = AsyncMock()
        monkeypatch.setattr(svc.pot_service, "attach_holding", attach)
        return attach

    @pytest.mark.asyncio
    async def test_the_units_issued_are_the_holdings_value_at_the_pots_own_price(self, monkeypatch):
        # The invariant the whole flow exists for, at its smallest: 100 units outstanding against a NAV
        # of 110 is a price of 1.10, so a holding worth 55 buys exactly 50 units — and 50 units at 1.10
        # is 55, which is what the contributor put in. Nobody else's value moves; only percentages do.
        created = _arrange(monkeypatch)
        self._wire(monkeypatch)
        await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)
        event = created.await_args.args[1]
        assert event.units == Decimal("50")
        assert event.unit_price == Decimal("1.10")
        assert event.base_amount == Decimal("55")

    @pytest.mark.asyncio
    async def test_the_row_is_a_contribution_for_the_callers_own_seat_dated_today_with_no_account_legs(self, monkeypatch):
        # Four properties in one row because they are one decision: the asset moved, so no money passed
        # between accounts; it is the caller's asset, so it is the caller's seat; and it is priced where
        # it stands, so the date is today and not a field the caller supplies.
        #
        # The NULL legs are the load-bearing one and the reason is not obvious. Two money queries turn
        # an ownership event into account movements — the balance union's `_FROM_AMOUNT`/`_TO_AMOUNT`
        # and the per-account ledger's `_ownership_branch` — and both branch on `type == contribution`
        # while keying on these two columns. Naming a leg "helpfully" (the pot account an account
        # contribution just became) would credit it `base_amount` ON TOP of the balance it already
        # carries, so the pot would gain the same money twice. The integration suite pins the figure;
        # this pins the shape.
        created = _arrange(monkeypatch)
        self._wire(monkeypatch)
        await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)
        event = created.await_args.args[1]
        assert event.type == OwnershipEventType.contribution
        assert event.member_id == SEAT.id
        assert event.date == date.today()
        assert (event.from_account_id, event.to_account_id) == (None, None)

    @pytest.mark.asyncio
    async def test_the_holdings_own_figure_and_currency_are_recorded_beside_the_credited_one(self, monkeypatch):
        # Both sides, no stored rate — the same shape a cross-currency money movement takes. 66,000 ARS
        # arriving as 55 USD buys the same 50 units, because units come from the CREDITED figure.
        created = _arrange(monkeypatch)
        self._wire(monkeypatch, valued=self._valued(value="66000", currency="ARS", base_value="55"))
        await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)
        event = created.await_args.args[1]
        assert (event.amount, event.amount_currency, event.base_amount) == (Decimal("66000"), "ARS", Decimal("55"))
        assert event.units == Decimal("50")

    @pytest.mark.asyncio
    async def test_a_holding_already_in_the_pots_currency_stores_no_currency_at_all(self, monkeypatch):
        # The column means "a real conversion happened", so it stays null whenever nothing was converted
        # — exactly what record_movement does with the same column.
        created = _arrange(monkeypatch)
        self._wire(monkeypatch)
        await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)
        assert created.await_args.args[1].amount_currency is None

    @pytest.mark.asyncio
    async def test_the_holding_is_valued_as_at_today_and_really_does_move(self, monkeypatch):
        # That the move happens at all, and that both halves speak about the same date. The ORDER of
        # the two — which is what decides whether the arithmetic is right — is asserted in
        # test_shared_write_ordering.py, where an order assertion has the tracing to be meaningful.
        _arrange(monkeypatch)
        attach = self._wire(monkeypatch)
        await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)
        attach.assert_awaited_once()
        assert svc.pot_service.value_contributed_holding.await_args.kwargs["as_of_date"] == date.today()

    @pytest.mark.asyncio
    async def test_an_undivided_pot_is_refused_because_there_is_no_price(self, monkeypatch):
        # With no units outstanding there is no unit price, so there is nothing to issue against — and
        # an undivided pot has the plain move-in for exactly this case.
        _arrange(monkeypatch, events=[])
        self._wire(monkeypatch)
        with pytest.raises(PotNotOpenedError):
            await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)

    @pytest.mark.asyncio
    async def test_a_pot_with_no_known_value_is_refused_rather_than_priced_at_a_guess(self, monkeypatch):
        _arrange(monkeypatch, nav=None)
        self._wire(monkeypatch)
        with pytest.raises(PotValuationRequiredError):
            await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)

    @pytest.mark.asyncio
    async def test_a_read_only_seat_cannot_contribute(self, monkeypatch):
        _arrange(monkeypatch)
        self._wire(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_writable", AsyncMock(side_effect=PotWriteRequiredError()))
        with pytest.raises(PotWriteRequiredError):
            await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)

    @pytest.mark.asyncio
    async def test_it_announces_the_credited_figure_in_the_pots_currency(self, monkeypatch):
        # The same sentence a money contribution sends, and the same figure: what changed for every
        # reader is what the pot took in, which for a cross-currency holding is not the number the
        # contributor would recognise as its price.
        _arrange(monkeypatch)
        self._wire(monkeypatch, valued=self._valued(value="66000", currency="ARS", base_value="55"))
        await svc.contribute_holding(AsyncMock(), 5, USER, investment_id=12)
        event, _recipients, payload = _DISPATCHED.await_args.args
        assert event == NotificationEvent.pot_movement
        assert payload["variant"] == "contribution"
        assert (payload["amount"], payload["currency"]) == ("55", "USD")
        assert payload["member"] == SEAT.display_name


class TestWholeShareWithdrawal:
    # Two owners holding 2 and 1 of 3 units, valued at 100 — so the price is 33.333333 and the larger
    # holder's share is reported as 66.67.
    @staticmethod
    def _thirds(monkeypatch):
        return _arrange(
            monkeypatch,
            events=[_event(member_id=100, units=Decimal("2")), _event(id=2, member_id=101, units=Decimal("1"))],
            nav=Decimal("100"),
        )

    @pytest.mark.asyncio
    async def test_the_share_value_a_holder_is_shown_is_refused_as_a_plain_withdrawal(self, monkeypatch):
        # Asking to take out precisely what the app says your share is worth, refused for holding too
        # little. This is the state the flag exists to remove, so it is asserted rather than described.
        created = self._thirds(monkeypatch)
        with pytest.raises(PotInsufficientUnitsError) as excinfo:
            await svc.record_movement(
                AsyncMock(), 5, USER, type=OwnershipEventType.withdrawal, date=date(2026, 6, 1), member_id=100, amount=Decimal("66.67")
            )
        assert excinfo.value.extra == {"held": "2", "requested": "2.000100"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_same_withdrawal_as_a_WHOLE_SHARE_redeems_the_exact_balance(self, monkeypatch):
        created = self._thirds(monkeypatch)
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.withdrawal,
            date=date(2026, 6, 1),
            member_id=100,
            amount=Decimal("66.67"),
            whole_share=True,
        )
        # Exactly the balance negated, so the replay nets it to zero and drops the seat. One unit
        # millionth either way would leave a 0.00% owner on every screen for good.
        assert created.await_args.args[1].units == Decimal("-2")

    @pytest.mark.asyncio
    async def test_the_money_recorded_is_what_moved_and_is_not_re_derived_from_the_units(self, monkeypatch):
        # The two may honestly disagree: someone may accept less than their share is worth to exit.
        # The event stores the price it was taken at, so the ledger says which figure is which.
        created = self._thirds(monkeypatch)
        await svc.record_movement(
            AsyncMock(),
            5,
            USER,
            type=OwnershipEventType.withdrawal,
            date=date(2026, 6, 1),
            member_id=100,
            amount=Decimal("50.00"),
            whole_share=True,
        )
        written = created.await_args.args[1]
        assert (written.amount, written.base_amount, written.units, written.unit_price) == (
            Decimal("50.00"),
            Decimal("50.00"),
            Decimal("-2"),
            Decimal("33.333333"),
        )

    @pytest.mark.asyncio
    async def test_a_member_holding_nothing_has_no_whole_share_to_take_out(self, monkeypatch):
        # replay_units drops a zero balance, so the seat is simply absent — which must refuse rather
        # than write an event moving no units at all.
        created = _arrange(monkeypatch, events=[_event(member_id=101, units=Decimal("100"))])
        with pytest.raises(PotInsufficientUnitsError) as excinfo:
            await svc.record_movement(
                AsyncMock(),
                5,
                USER,
                type=OwnershipEventType.withdrawal,
                date=date(2026, 6, 1),
                member_id=100,
                amount=Decimal("5"),
                whole_share=True,
            )
        assert excinfo.value.extra["held"] == "0"
        created.assert_not_awaited()


class TestDeletion:
    @pytest.mark.asyncio
    async def test_deleting_an_OPENING_takes_the_whole_baseline(self, monkeypatch):
        """The baseline is ONE act written as one row per owner, so it can only be undone as one act.

        Deleting a single row of it leaves a division summing to less than the value it recorded and
        silently hands the remaining owners a share nobody agreed to — a 60/40 pot reads 100/0 — and it
        cannot be repaired, because record_opening refuses while any opening row survives. The only way
        back would be a re-agreement, which records a gift that never happened.
        """
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=_event(type=OwnershipEventType.opening)))
        delete_one = AsyncMock()
        delete_all = AsyncMock(return_value=2)
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
        monkeypatch.setattr(svc.pot_ownership_repository, "delete_openings", delete_all)

        assert await svc.delete_event(AsyncMock(), 5, 1, USER) == 2
        # Asserted on which repository call the service made, not on a count a stub handed back.
        delete_one.assert_not_awaited()
        assert delete_all.await_args.args[1] == 5

    @pytest.mark.asyncio
    async def test_every_other_event_type_deletes_only_itself(self, monkeypatch):
        # The counterweight, and the reason the rule is scoped to openings: a contribution, a withdrawal
        # and a re-agreement are each ONE event, so taking siblings with them would delete history the
        # user did not touch.
        for kind in (OwnershipEventType.contribution, OwnershipEventType.withdrawal, OwnershipEventType.reagreement):
            _arrange(monkeypatch)
            monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=_event(type=kind)))
            delete_one = AsyncMock()
            delete_all = AsyncMock(return_value=9)
            monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
            monkeypatch.setattr(svc.pot_ownership_repository, "delete_openings", delete_all)

            assert await svc.delete_event(AsyncMock(), 5, 1, USER) == 1, kind
            delete_all.assert_not_awaited()
            delete_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deleting_needs_pot_write_access(self, monkeypatch):
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, READER)))
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=_event(type=OwnershipEventType.contribution)))
        delete_one = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
        with pytest.raises(PotWriteRequiredError):
            await svc.delete_event(AsyncMock(), 5, 1, USER)
        delete_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_named_counterparty_may_delete_a_reagreement_without_write_access(self, monkeypatch):
        """The remedy, and the reason it has to exist: write access is not granted by ownership.

        create_pot inserts can_write for the CREATOR only and recording the opening grants nobody else
        write, so the default state of a divided pot is that its creator can move units away from a
        co-owner who is notified by name and can do nothing about it.
        """
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, OTHER_SEAT, READER)))
        # OTHER_SEAT is the counterparty: the seat this re-agreement moved units TO.
        event = _event(type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=event))
        delete_one = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)

        assert await svc.delete_event(AsyncMock(), 5, 1, USER) == 1
        delete_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_giver_of_a_reagreement_may_delete_it_too(self, monkeypatch):
        # Both named seats, not only the one who lost units: the pair agreed to the split, so either of
        # them may take the record of it back.
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, READER)))
        event = _event(type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=event))
        delete_one = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)

        assert await svc.delete_event(AsyncMock(), 5, 1, USER) == 1
        delete_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_widening_reaches_no_other_event_type(self, monkeypatch):
        """Only a re-agreement, and the reason is what makes one different from the other three.

        A contribution and a withdrawal move the mover's OWN money, and an opening is the division
        everybody agreed to — none of them has a counterparty with a claim to undo it. The event this
        loop builds names the reader on both member columns, so the ONLY thing keeping the delete out is
        the type check.
        """
        for kind in (OwnershipEventType.opening, OwnershipEventType.contribution, OwnershipEventType.withdrawal):
            _arrange(monkeypatch)
            monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, READER)))
            event = _event(type=kind, member_id=SEAT.id, counterparty_member_id=SEAT.id)
            monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=event))
            delete_one = AsyncMock()
            delete_all = AsyncMock(return_value=2)
            monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
            monkeypatch.setattr(svc.pot_ownership_repository, "delete_openings", delete_all)
            with pytest.raises(PotWriteRequiredError):
                await svc.delete_event(AsyncMock(), 5, 1, USER)
            delete_one.assert_not_awaited()
            delete_all.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_member_named_on_neither_side_may_not_delete_a_reagreement(self, monkeypatch):
        # The other half of the narrowing: being able to SEE the pot is not being party to the deal.
        _arrange(monkeypatch)
        third = GroupMember(id=102, group_id=10, user_id=3, display_name="Leo", role=GroupMemberRole.member)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, third, READER)))
        event = _event(type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=event))
        delete_one = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
        with pytest.raises(PotWriteRequiredError):
            await svc.delete_event(AsyncMock(), 5, 1, USER)
        delete_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_event_id_from_another_pot_is_not_found(self, monkeypatch):
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=None))
        delete_one = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
        with pytest.raises(NotFoundError):
            await svc.delete_event(AsyncMock(), 5, 999, USER)
        delete_one.assert_not_awaited()


class TestWhoConfirmsAReagreement:
    """The affected seat, resolved as ONE expression rather than a set of eligible seats.

    The giver, unless the giver recorded the change, in which case the receiver. What the single
    expression buys is the case a set would get wrong: a third party with write access recording a
    change between two other members, where a set of "both named seats" would let the member who GAINED
    units lock the member who lost them out of their remedy.

    The SQL policy carries the same expression clause for clause, and test_rls_pot_scope pins the two
    together — this file only proves the Python half.
    """

    ROSTER = {SEAT.id: SEAT, OTHER_SEAT.id: OTHER_SEAT}

    def _swap(self, **kwargs) -> PotOwnershipEvent:
        return _event(type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id, **kwargs)

    def test_a_third_party_recording_it_leaves_the_answer_on_the_GIVER(self):
        # The case the whole rule exists for. USER (3) is neither seat, so the seat with something taken
        # is the one whose agreement is worth having — and a set of both seats would let the RECEIVER
        # confirm and take the giver's remedy away.
        assert svc._confirming_member_id(self._swap(created_by=3), self.ROSTER) == SEAT.id

    def test_the_giver_recording_it_hands_the_answer_to_the_RECEIVER(self):
        # Nobody vouches for their own act, which is the whole point of a confirm.
        assert svc._confirming_member_id(self._swap(created_by=SEAT.user_id), self.ROSTER) == OTHER_SEAT.id

    def test_the_receiver_recording_it_leaves_the_answer_on_the_giver(self):
        assert svc._confirming_member_id(self._swap(created_by=OTHER_SEAT.user_id), self.ROSTER) == SEAT.id

    def test_a_recorder_whose_account_is_gone_leaves_the_answer_on_the_giver(self):
        # created_by is SET NULL on account deletion. A NULL on either side of the comparison yields
        # NULL, falls to the ELSE, and leaves the answer on the seat with something taken — which is the
        # safe direction, and the one the SQL's plain equality produces too.
        assert svc._confirming_member_id(self._swap(created_by=None), self.ROSTER) == SEAT.id

    def test_a_NAME_ONLY_giver_keeps_the_answer_and_so_nobody_can_confirm(self):
        # D34's posture for a settlement, unchanged: a name-only seat has no account, so the answer names
        # a member id no request can ever be. Such a re-agreement is simply never confirmable, and stays
        # deletable by the real seat instead — which is better than handing the confirm to the other side.
        placeholder = GroupMember(id=103, group_id=10, user_id=None, display_name="Ana (no account)", role=GroupMemberRole.member)
        event = _event(type=OwnershipEventType.reagreement, member_id=placeholder.id, counterparty_member_id=SEAT.id, created_by=SEAT.user_id)
        assert svc._confirming_member_id(event, {placeholder.id: placeholder, SEAT.id: SEAT}) == placeholder.id

    def test_no_other_event_type_carries_a_confirmation_at_all(self):
        # The same narrowing the DELETE remedy has, and the same reason: a contribution or a withdrawal
        # moves the mover's own money and an opening is the division everybody agreed to, so none of them
        # has an affected seat whose agreement means anything. A table CHECK says it too.
        for kind in (OwnershipEventType.opening, OwnershipEventType.contribution, OwnershipEventType.withdrawal):
            event = _event(type=kind, member_id=SEAT.id, created_by=3)
            assert svc._confirming_member_id(event, self.ROSTER) is None, kind


class TestConfirmation:
    def _swap(self, **kwargs) -> PotOwnershipEvent:
        # Recorded by USER, who is SEAT — so the affected seat is OTHER_SEAT, the receiver.
        return _event(
            type=OwnershipEventType.reagreement,
            member_id=SEAT.id,
            counterparty_member_id=OTHER_SEAT.id,
            created_by=USER.id,
            **kwargs,
        )

    # The affected seat's own request: OTHER_SEAT, holding NO write access, which is the configuration
    # the whole decision is about — write access is granted to a pot's creator and nobody else.
    def _as_affected_seat(self, monkeypatch, event: PotOwnershipEvent):
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, OTHER_SEAT, READER)))
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=event))
        saved = AsyncMock(side_effect=lambda _s, e: e)
        monkeypatch.setattr(svc.pot_ownership_repository, "save", saved)
        monkeypatch.setattr(svc.shared_audit_service, "record", AsyncMock())
        return saved

    @pytest.mark.asyncio
    async def test_a_read_only_affected_seat_may_confirm(self, monkeypatch):
        """The point of the unit, stated as a test.

        A co-owner with no write access is exactly who this is for: the pot's creator can move units away
        from them, they are notified by name, and until PR 10 they could do nothing. Gating the confirm on
        write access would have refused the only person entitled to answer.
        """
        event = self._swap()
        saved = self._as_affected_seat(monkeypatch, event)
        response = await svc.confirm_event(AsyncMock(), 5, 1, USER)
        assert event.confirmed_at is not None
        saved.assert_awaited_once()
        assert response.confirmed_at is not None
        # And the seat that just gave it is the one offered the way back out, nobody else.
        assert (response.can_confirm, response.can_unconfirm, response.can_delete) == (False, True, False)

    @pytest.mark.asyncio
    async def test_confirming_is_audited_as_its_own_action_naming_both_seats(self, monkeypatch):
        event = self._swap()
        self._as_affected_seat(monkeypatch, event)
        recorded = AsyncMock()
        monkeypatch.setattr(svc.shared_audit_service, "record", recorded)
        await svc.confirm_event(AsyncMock(), 5, 1, USER)
        kwargs = recorded.await_args.kwargs
        assert kwargs["action"] == AuditAction.confirmed
        assert kwargs["entity_type"] == AuditEntityType.ownership_event
        # The pot id is what makes the entry as hidden as the pot itself.
        assert kwargs["pot_id"] == POT.id
        assert (kwargs["payload"]["member"], kwargs["payload"]["counterparty"]) == (SEAT.display_name, OTHER_SEAT.display_name)

    @pytest.mark.asyncio
    async def test_confirming_announces_it_as_an_ownership_change_variant(self, monkeypatch):
        # ownership_changed with a variant rather than an event of its own, so somebody who has switched
        # pot-ownership news off stays switched off for the confirmation too — and `notification_event`
        # is a Postgres enum, so a new value would be a migration for a sentence.
        self._as_affected_seat(monkeypatch, self._swap())
        await svc.confirm_event(AsyncMock(), 5, 1, USER)
        event, recipients, payload = _DISPATCHED.await_args.args
        assert event == NotificationEvent.ownership_changed
        assert payload["variant"] == "confirmed"
        assert (payload["from_member"], payload["to_member"]) == (SEAT.display_name, OTHER_SEAT.display_name)
        # The actor is the seat that agreed, and they are excluded from their own announcement.
        assert payload["actor"] == OTHER_SEAT.display_name
        assert recipients == [OTHER_SEAT.user_id]

    @pytest.mark.asyncio
    async def test_no_figure_is_announced(self, monkeypatch):
        # What was agreed is a change of UNITS, a quantity no surface shows a person (U2), and the
        # percentage it corresponds to is not stored on the event. Any figure here would be a second
        # answer to a question the pot page already answers.
        self._as_affected_seat(monkeypatch, self._swap())
        await svc.confirm_event(AsyncMock(), 5, 1, USER)
        payload = _DISPATCHED.await_args.args[2]
        assert "amount" not in payload and "currency" not in payload

    @pytest.mark.asyncio
    async def test_the_seat_that_RECORDED_it_cannot_confirm_their_own_act(self, monkeypatch):
        # SEAT recorded this one, so the answer moved to OTHER_SEAT — and a writer asking anyway is
        # refused, which is what makes write access not the trust boundary.
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=self._swap()))
        saved = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "save", saved)
        with pytest.raises(PotReagreementNotYoursError):
            await svc.confirm_event(AsyncMock(), 5, 1, USER)
        saved.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_member_named_on_neither_side_cannot_confirm(self, monkeypatch):
        # Seeing the pot is not being party to the deal — the same narrowing the delete remedy has.
        _arrange(monkeypatch)
        third = GroupMember(id=102, group_id=10, user_id=3, display_name="Leo", role=GroupMemberRole.member)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, third, WRITER)))
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=self._swap()))
        saved = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "save", saved)
        with pytest.raises(PotReagreementNotYoursError):
            await svc.confirm_event(AsyncMock(), 5, 1, USER)
        saved.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_other_event_type_can_be_confirmed(self, monkeypatch):
        # Reachable only by naming another event's id on the confirm route, which is why it is a coded
        # refusal rather than a 422 — and a table CHECK refuses the row underneath it.
        for kind in (OwnershipEventType.opening, OwnershipEventType.contribution, OwnershipEventType.withdrawal):
            _arrange(monkeypatch)
            monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=_event(type=kind)))
            saved = AsyncMock()
            monkeypatch.setattr(svc.pot_ownership_repository, "save", saved)
            with pytest.raises(PotEventNotConfirmableError):
                await svc.confirm_event(AsyncMock(), 5, 1, USER)
            saved.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirming_twice_is_refused(self, monkeypatch):
        event = self._swap(confirmed_at=datetime(2026, 9, 1, 12, 0))
        saved = self._as_affected_seat(monkeypatch, event)
        with pytest.raises(PotReagreementConfirmedError):
            await svc.confirm_event(AsyncMock(), 5, 1, USER)
        saved.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_event_id_from_another_pot_is_not_found(self, monkeypatch):
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await svc.confirm_event(AsyncMock(), 5, 999, USER)


class TestWithdrawingAConfirmation:
    def _confirmed(self, *, confirmed_at: datetime | None = datetime(2026, 9, 1, 12, 0)) -> PotOwnershipEvent:
        return _event(
            type=OwnershipEventType.reagreement,
            member_id=SEAT.id,
            counterparty_member_id=OTHER_SEAT.id,
            created_by=USER.id,
            confirmed_at=confirmed_at,
        )

    def _as_affected_seat(self, monkeypatch, event: PotOwnershipEvent, *, permission=READER):
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, OTHER_SEAT, permission)))
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=event))
        saved = AsyncMock(side_effect=lambda _s, e: e)
        monkeypatch.setattr(svc.pot_ownership_repository, "save", saved)
        monkeypatch.setattr(svc.shared_audit_service, "record", AsyncMock())
        return saved

    @pytest.mark.asyncio
    async def test_the_seat_that_gave_it_may_take_it_back(self, monkeypatch):
        # The ONLY way out of a confirmed re-agreement, which nobody can delete. Left underivable, one
        # confirmed by mistake would have no exit at all.
        event = self._confirmed()
        saved = self._as_affected_seat(monkeypatch, event)
        response = await svc.unconfirm_event(AsyncMock(), 5, 1, USER)
        assert event.confirmed_at is None
        saved.assert_awaited_once()
        assert response.confirmed_at is None
        # Back to deletable by the seat's own remedy, and offered the confirm again.
        assert (response.can_confirm, response.can_unconfirm, response.can_delete) == (True, False, True)

    @pytest.mark.asyncio
    async def test_it_is_audited_and_announced_as_its_own_thing(self, monkeypatch):
        """Announced too, unlike a settlement's un-confirm, which tells nobody.

        Withdrawing a confirmation RE-ARMS a deletion the lock had closed off, so the other seat's
        standing genuinely changes — and they cannot see it happen on a page they are not looking at.
        """
        self._as_affected_seat(monkeypatch, self._confirmed())
        recorded = AsyncMock()
        monkeypatch.setattr(svc.shared_audit_service, "record", recorded)
        await svc.unconfirm_event(AsyncMock(), 5, 1, USER)
        assert recorded.await_args.kwargs["action"] == AuditAction.unconfirmed
        event, _, payload = _DISPATCHED.await_args.args
        assert event == NotificationEvent.ownership_changed
        assert payload["variant"] == "unconfirmed"

    @pytest.mark.asyncio
    async def test_there_is_nothing_to_take_back_on_an_unconfirmed_entry(self, monkeypatch):
        # Mirrors unconfirm_settlement's answer for the same state, and nothing in the app offers the
        # action on a row that has none.
        saved = self._as_affected_seat(monkeypatch, self._confirmed(confirmed_at=None))
        with pytest.raises(NotFoundError):
            await svc.unconfirm_event(AsyncMock(), 5, 1, USER)
        saved.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nobody_else_may_take_it_back_not_even_a_writer(self, monkeypatch):
        # It is their word being withdrawn, so it is theirs to withdraw. A pot writer asking is refused
        # for the same reason they cannot give it.
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=self._confirmed()))
        saved = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "save", saved)
        with pytest.raises(PotReagreementNotYoursError):
            await svc.unconfirm_event(AsyncMock(), 5, 1, USER)
        saved.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_seat_that_also_holds_write_access_is_told_it_may_delete_again(self, monkeypatch):
        # The affected seat may ALSO be a writer, which is why the confirm path resolves real write
        # access rather than assuming it has none: reporting can_delete false here would hide an action
        # the caller genuinely has the moment the lock comes off.
        writer_seat = PotMemberPermission(pot_id=5, member_id=OTHER_SEAT.id, can_view=True, can_write=True)
        self._as_affected_seat(monkeypatch, self._confirmed(), permission=writer_seat)
        response = await svc.unconfirm_event(AsyncMock(), 5, 1, USER)
        assert response.can_delete is True


class TestWhatTheLedgerResponseSaysAboutEachRow:
    """The three permission fields, read off the ledger list as the surface reads them.

    They live on the response rather than being mirrored on the web for two reasons: `can_confirm`
    could not be derived by a client at all (the rule reads `created_by`, which the response
    deliberately does not carry), and `can_delete` now has confirmation as one of its clauses — so
    splitting them would put half of one rule in each of two places.
    """

    def _list_as(self, monkeypatch, seat: GroupMember, permission, events: list[PotOwnershipEvent]):
        _arrange(monkeypatch, events=events)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, seat, permission)))
        return events

    @pytest.mark.asyncio
    async def test_the_affected_seat_is_offered_the_confirm_and_nobody_else_is(self, monkeypatch):
        # Recorded by SEAT, so OTHER_SEAT is the affected seat. Both reads run over the SAME row, so the
        # difference is the rule and not the fixture.
        swap = _event(type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id, created_by=USER.id)
        self._list_as(monkeypatch, OTHER_SEAT, READER, [swap])
        affected = (await svc.list_events(AsyncMock(), 5, USER))[0]
        assert (affected.can_confirm, affected.can_unconfirm) == (True, False)

        self._list_as(monkeypatch, SEAT, WRITER, [swap])
        recorder = (await svc.list_events(AsyncMock(), 5, USER))[0]
        assert (recorder.can_confirm, recorder.can_unconfirm) == (False, False)

    @pytest.mark.asyncio
    async def test_a_read_only_seat_may_delete_the_reagreement_it_is_named_on_and_nothing_else(self, monkeypatch):
        # PR 10's remedy, read off the response. The opening in the same list is what proves the answer
        # is per-ROW rather than per-caller.
        swap = _event(id=2, type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id)
        self._list_as(monkeypatch, OTHER_SEAT, READER, [_event(id=1), swap])
        opening, reagreement = await svc.list_events(AsyncMock(), 5, USER)
        assert (opening.can_delete, reagreement.can_delete) == (False, True)

    @pytest.mark.asyncio
    async def test_a_confirmed_row_reports_itself_undeletable_to_a_writer(self, monkeypatch):
        # The lock, as the button sees it: the same writer who may delete every other row is told no here.
        swap = _event(id=2, type=OwnershipEventType.reagreement, member_id=SEAT.id, counterparty_member_id=OTHER_SEAT.id)
        confirmed = _event(
            id=3,
            type=OwnershipEventType.reagreement,
            member_id=SEAT.id,
            counterparty_member_id=OTHER_SEAT.id,
            confirmed_at=datetime(2026, 9, 1, 12, 0),
        )
        self._list_as(monkeypatch, SEAT, WRITER, [swap, confirmed])
        unconfirmed_row, confirmed_row = await svc.list_events(AsyncMock(), 5, USER)
        assert (unconfirmed_row.can_delete, confirmed_row.can_delete) == (True, False)
        # And the timestamp travels, because it is what the row's badge states.
        assert confirmed_row.confirmed_at is not None and unconfirmed_row.confirmed_at is None


class TestTheLockOnDeletion:
    """Confirming closes the delete for EVERYBODY, which is what makes it the trust anchor.

    It changes no arithmetic — a re-agreement counted from the moment it was recorded — so the lock IS
    what confirmation buys. Both DELETE policies carry the same clause, so the database refuses these
    too rather than leaving the service the only guard.
    """

    def _confirmed(self) -> PotOwnershipEvent:
        return _event(
            type=OwnershipEventType.reagreement,
            member_id=SEAT.id,
            counterparty_member_id=OTHER_SEAT.id,
            confirmed_at=datetime(2026, 9, 1, 12, 0),
        )

    @pytest.mark.asyncio
    async def test_a_pot_WRITER_cannot_delete_a_confirmed_reagreement(self, monkeypatch):
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=self._confirmed()))
        delete_one = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
        # The refusal names the one way out rather than talking about write access, which the caller has.
        with pytest.raises(PotReagreementConfirmedError):
            await svc.delete_event(AsyncMock(), 5, 1, USER)
        delete_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_neither_named_seat_can_delete_it_either(self, monkeypatch):
        # The remedy is what a seat has BEFORE they agree, and agreeing is what gives it up.
        for seat in (SEAT, OTHER_SEAT):
            _arrange(monkeypatch)
            monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, seat, READER)))
            monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=self._confirmed()))
            delete_one = AsyncMock()
            monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete_one)
            with pytest.raises(PotReagreementConfirmedError):
                await svc.delete_event(AsyncMock(), 5, 1, USER)
            delete_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_refusal_is_the_write_access_one_when_the_row_is_not_confirmed(self, monkeypatch):
        # Which error, from the row's own state. Both branches asserted, because one message pointing at
        # a confirmation nobody gave would be a dead end.
        _arrange(monkeypatch)
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, READER)))
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", AsyncMock(return_value=_event(type=OwnershipEventType.contribution)))
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", AsyncMock())
        with pytest.raises(PotWriteRequiredError):
            await svc.delete_event(AsyncMock(), 5, 1, USER)


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


# Handing over the WHOLE of a stake, which is what a buy-out does. `percentage=None` is the input for
# it, and the pair below shows why it is a separate input rather than sugar: the giver's own share,
# rounded to the two decimals the request body allows and multiplied back out, overshoots their
# balance. Measured over 200,000 plausible pots, it lands on the balance 18 times.
class TestWholeStakeReagreement:
    # A giver holding 2 of 3 units, so their share rounds to 66.67% and 66.67% of 3 is 2.000100.
    @staticmethod
    def _thirds(monkeypatch):
        return _arrange(
            monkeypatch,
            events=[_event(member_id=100, units=Decimal("2")), _event(id=2, member_id=101, units=Decimal("1"))],
            nav=Decimal("100"),
        )

    @pytest.mark.asyncio
    async def test_the_givers_own_share_as_a_percentage_overshoots_their_balance(self, monkeypatch):
        created = self._thirds(monkeypatch)
        with pytest.raises(PotInsufficientUnitsError) as excinfo:
            await svc.record_reagreement(
                AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=Decimal("66.67")
            )
        assert excinfo.value.extra == {"held": "2", "requested": "2.000100"}
        created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_WHOLE_STAKE_moves_the_exact_balance_instead(self, monkeypatch):
        created = self._thirds(monkeypatch)
        await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=None)
        written = created.await_args.args[1]
        # Signed against the giver, and the counterparty receives exactly the negation — so the giver
        # nets to zero and the buyer ends up holding every unit that was outstanding.
        assert (written.member_id, written.counterparty_member_id, written.units) == (100, 101, Decimal("-2"))
        assert (written.amount, written.base_amount) == (None, None)

    @pytest.mark.asyncio
    async def test_a_percentage_JUST_UNDER_the_stake_still_leaves_a_residual(self, monkeypatch):
        # The other half of the failure: rounding the other way is accepted and leaves the seller
        # holding units. Asserted because a residual is not cosmetic — replay_units drops only an
        # exact zero, so it renders as a 0.00% owner worth 0.00 forever.
        created = self._thirds(monkeypatch)
        await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=Decimal("66.66"))
        assert created.await_args.args[1].units == Decimal("-1.999800")

    @pytest.mark.asyncio
    async def test_a_member_holding_nothing_has_no_stake_to_hand_over(self, monkeypatch):
        created = _arrange(monkeypatch, events=[_event(member_id=101, units=Decimal("100"))])
        with pytest.raises(PotInsufficientUnitsError) as excinfo:
            await svc.record_reagreement(AsyncMock(), 5, USER, date=date(2026, 6, 1), from_member_id=100, to_member_id=101, percentage=None)
        assert excinfo.value.extra["held"] == "0"
        created.assert_not_awaited()


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
    async def test_deleting_an_event_is_refused_to_someone_who_cannot_see_the_pot(self, monkeypatch):
        # The gate moved from require_writable to require_VISIBLE when the counterparty remedy landed,
        # so this is what now stops a stranger: invisible reads back as absent, never as forbidden.
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(side_effect=NotFoundError("Pot not found")))
        with pytest.raises(NotFoundError):
            await svc.delete_event(AsyncMock(), 5, 1, USER)

    @pytest.mark.asyncio
    async def test_an_event_is_looked_up_scoped_to_its_own_pot(self, monkeypatch):
        # Asserted on the ARGUMENTS the service passed, not on what the stub handed back. A stub
        # returning None passes whatever the service asks for, so "it raised NotFoundError" would be
        # true even if the pot id were never part of the lookup at all — which is exactly how an event
        # id from another pot would become reachable by guessing.
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, WRITER)))
        monkeypatch.setattr(svc.pot_repository, "lock", AsyncMock())
        get_by_id = AsyncMock(return_value=None)
        monkeypatch.setattr(svc.pot_ownership_repository, "get_by_id", get_by_id)
        delete = AsyncMock()
        monkeypatch.setattr(svc.pot_ownership_repository, "delete", delete)
        with pytest.raises(NotFoundError):
            await svc.delete_event(AsyncMock(), 5, 999, USER)
        assert get_by_id.await_args.args[1:] == (POT.id, 999)
        delete.assert_not_awaited()
