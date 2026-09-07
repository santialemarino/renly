# Pot visibility, write access, and the guards around moving holdings between scopes.
#
# The visibility rules here are the SECOND copy of a decision the database also makes: _may_view
# mirrors the app_can_view_pot SQL helper exactly. Both are tested — this file for the service, and
# tests/integration/test_rls_isolation.py for the policy — because the failure that matters is the two
# disagreeing, and only one of them is reachable from a unit test.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    AccountHasLinkedEntriesError,
    ExchangeRateUnavailableError,
    NotFoundError,
    PotHasHoldingsError,
    PotHoldingAddDividedError,
    PotHoldingInactiveError,
    PotHoldingNotPositiveError,
    PotHoldingUnvaluedError,
    PotValuation,
    PotWriteRequiredError,
)
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.investment import Investment, InvestmentCategory
from app.models.pot import OwnershipEventType, Pot, PotCadence, PotMemberPermission, PotOwnershipEvent, PotVisibility
from app.models.snapshot import InvestmentSnapshot
from app.models.user import User
from app.schemas.pot import PotHoldingResponse
from app.services import pot_service
from app.utils.metrics import RateLookup

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
OTHER = User(id=2, name="Ana", email="a@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
PLAIN_SEAT = GroupMember(id=101, group_id=10, user_id=OTHER.id, display_name="Ana", role=GroupMemberRole.member)


def _pot(**kwargs) -> Pot:
    defaults = dict(id=5, group_id=10, name=None, base_currency="USD", visibility=PotVisibility.members, is_default=True)
    return Pot(**{**defaults, **kwargs})


# A pot-held investment as the valuation now reads it: whole rows, because each holding is labelled
# with the composition bucket it contributes to. Category is incidental here — nothing in this file is
# about the bucket.
def _pot_investment(investment_id: int) -> Investment:
    return Investment(id=investment_id, user_id=None, pot_id=5, name=f"I{investment_id}", category=InvestmentCategory.fci, base_currency="USD")


# A rate lookup with nothing in it: every fixture in the picker tests is single-currency, so no
# conversion is ever reached and an empty one proves the figures came from the holdings themselves
# rather than from a rate.
_LOOKUP = RateLookup(dollar_preference=None, rates_by_pair={})


# The one ledger row the picker replays to learn how many units are outstanding: 100 at 1.00, which
# against a NAV of 110 is the same clean 1.10 price the ownership tests use.
def _opening_event() -> PotOwnershipEvent:
    return PotOwnershipEvent(
        id=1, pot_id=5, type=OwnershipEventType.opening, date=date(2026, 1, 1), member_id=100, units=Decimal("100"), unit_price=Decimal("1")
    )


def _permission(**kwargs) -> PotMemberPermission:
    defaults = dict(pot_id=5, member_id=100, can_view=True, can_write=False)
    return PotMemberPermission(**{**defaults, **kwargs})


# Every read the scope-boundary guard consults, as (repository, method) so the two scope-FREE ones sit
# in the same enumeration as the seven others rather than beside it. Stubbed clean here so a test can
# override the ONE it is about. Listed once rather than per test: a table added to the guard and not to
# this tuple makes all eight of those tests fail in one place, which is the point — the guard grew a
# blind spot twice, and both times it was a table nobody remembered it should ask.
_GUARDED_READS = (
    ("income_repository", "linked_account_ids"),
    ("expense_repository", "linked_account_ids"),
    ("card_settlement_repository", "linked_account_ids"),
    ("transfer_repository", "linked_account_ids"),
    ("shared_expense_repository", "linked_account_ids"),
    ("shared_income_repository", "linked_account_ids"),
    ("group_settlement_repository", "linked_account_ids"),
    ("transfer_repository", "linked_account_ids_any_scope"),
    ("pot_ownership_repository", "linked_account_ids"),
)


def _no_movements(monkeypatch) -> None:
    for repository, method in _GUARDED_READS:
        monkeypatch.setattr(getattr(pot_service, repository), method, AsyncMock(return_value=set()))


class TestVisibilityResolution:
    # The four rows of the §7 test matrix, at the service layer. Each one is also asserted against a
    # real Postgres policy in the integration suite.
    def test_a_members_pot_is_visible_with_no_permission_row_at_all(self):
        # The whole point of reading the pot's default here: a member who joined the group AFTER the
        # pot was created has no row, and V4 says they should still see a 'members' pot.
        assert pot_service._may_view(_pot(visibility=PotVisibility.members), None) is True

    def test_an_owners_pot_is_invisible_with_no_permission_row(self):
        # Fail-closed: no row, no access, until an ownership event or an admin writes one.
        assert pot_service._may_view(_pot(visibility=PotVisibility.owners), None) is False

    def test_an_explicit_row_beats_the_default_in_both_directions(self):
        assert pot_service._may_view(_pot(visibility=PotVisibility.members), _permission(can_view=False)) is False
        assert pot_service._may_view(_pot(visibility=PotVisibility.owners), _permission(can_view=True)) is True

    def test_write_has_no_visibility_style_default(self):
        # A pot with no permission rows is readable by its group and writable by nobody (V6).
        assert pot_service.may_write(None) is False
        assert pot_service.may_write(_permission(can_write=False)) is False
        assert pot_service.may_write(_permission(can_view=True, can_write=True)) is True


class TestVisibilityGate:
    @pytest.mark.asyncio
    async def test_a_non_member_gets_the_same_answer_as_a_missing_pot(self, monkeypatch):
        # Indistinguishable by design, so probing ids reveals nothing about pots that merely exist.
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot()))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await pot_service.require_visible(AsyncMock(), 5, OTHER)

    @pytest.mark.asyncio
    async def test_a_removed_member_loses_visibility_immediately(self, monkeypatch):
        removed = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", is_active=False)
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot()))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=removed))
        with pytest.raises(NotFoundError):
            await pot_service.require_visible(AsyncMock(), 5, USER)

    @pytest.mark.asyncio
    async def test_a_member_denied_view_gets_a_404_not_a_403(self, monkeypatch):
        # 403 would confirm the pot exists. A member who may not see it must not learn that.
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot()))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=_permission(can_view=False)))
        with pytest.raises(NotFoundError):
            await pot_service.require_visible(AsyncMock(), 5, USER)

    @pytest.mark.asyncio
    async def test_a_zero_percent_member_still_sees_the_pot(self, monkeypatch):
        # V3: membership is not ownership. Nothing in the visibility path consults the ledger at all,
        # which is what makes this true by construction rather than by a rule someone has to apply.
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot()))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=PLAIN_SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=None))
        pot, member, _ = await pot_service.require_visible(AsyncMock(), 5, OTHER)
        assert (pot.id, member.id) == (5, 101)

    @pytest.mark.asyncio
    async def test_a_read_only_member_is_refused_a_write_with_403(self, monkeypatch):
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot()))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=_permission(can_write=False)))
        with pytest.raises(PotWriteRequiredError):
            await pot_service.require_writable(AsyncMock(), 5, USER)

    @pytest.mark.asyncio
    async def test_being_a_group_admin_grants_no_view_of_its_pots(self, monkeypatch):
        # "Administration never grants visibility" (V2), asserted rather than assumed: SEAT is an
        # ADMIN, and an admin with can_view false sees exactly nothing.
        assert SEAT.role == GroupMemberRole.admin
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot(visibility=PotVisibility.owners)))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await pot_service.require_visible(AsyncMock(), 5, USER)


class TestPotCreation:
    @pytest.mark.asyncio
    async def test_the_creator_is_seated_with_full_access(self, monkeypatch):
        # Asserted on the row the service BUILT, not on what a mock handed back — a mock with a
        # hardcoded return value would pass even if the service granted nothing at all.
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "create", AsyncMock(side_effect=lambda _s, pot: pot))
        save_permission = AsyncMock(side_effect=lambda _s, p: p)
        monkeypatch.setattr(pot_service.pot_repository, "save_permission", save_permission)
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))

        session = AsyncMock()
        await pot_service.create_pot(session, 10, USER, base_currency="USD")

        written = save_permission.await_args.args[1]
        assert (written.member_id, written.can_view, written.can_write) == (SEAT.id, True, True)

    @pytest.mark.asyncio
    async def test_the_first_pot_in_a_group_is_its_default_and_a_later_one_is_not(self, monkeypatch):
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        created = AsyncMock(side_effect=lambda _s, pot: pot)
        monkeypatch.setattr(pot_service.pot_repository, "create", created)
        monkeypatch.setattr(pot_service.pot_repository, "save_permission", AsyncMock(side_effect=lambda _s, p: p))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))

        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", AsyncMock(return_value=[]))
        await pot_service.create_pot(AsyncMock(), 10, USER, base_currency="USD")
        assert created.await_args.args[1].is_default is True

        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", AsyncMock(return_value=[_pot()]))
        await pot_service.create_pot(AsyncMock(), 10, USER, base_currency="USD")
        assert created.await_args.args[1].is_default is False


class TestDeletion:
    @pytest.mark.asyncio
    async def test_a_pot_holding_anything_cannot_be_deleted(self, monkeypatch):
        # The database refuses it too (every pot_id FK is ON DELETE RESTRICT); this turns the refusal
        # into a message that says what to do about it.
        from app.services import group_service

        monkeypatch.setattr(pot_service, "require_visible", AsyncMock(return_value=(_pot(), SEAT, _permission())))
        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "count_holdings", AsyncMock(return_value=3))
        delete = AsyncMock()
        monkeypatch.setattr(pot_service.pot_repository, "delete", delete)
        with pytest.raises(PotHasHoldingsError) as excinfo:
            await pot_service.delete_pot(AsyncMock(), 5, USER)
        assert excinfo.value.extra == {"holding_count": 3}
        delete.assert_not_awaited()


class TestMovingHoldings:
    def _investment(self, id: int, *, user_id: int | None = 1, pot_id: int | None = None) -> Investment:
        return Investment(id=id, user_id=user_id, pot_id=pot_id, name="F", category=InvestmentCategory.fci, base_currency="USD")

    def _account(self, id: int, *, user_id: int | None = 1, pot_id: int | None = None) -> Account:
        return Account(id=id, user_id=user_id, pot_id=pot_id, name="A", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))

    @pytest.mark.asyncio
    async def test_moving_in_requires_pot_write_access(self, monkeypatch):
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(side_effect=PotWriteRequiredError()))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        with pytest.raises(PotWriteRequiredError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1])

    @pytest.mark.asyncio
    async def test_a_holding_that_is_not_the_callers_own_private_one_is_refused(self, monkeypatch):
        # Naming someone else's id must not co-opt their money into a pot they never agreed to share.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pot_service.investment_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._investment(1, user_id=OTHER.id)])
        )
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        with pytest.raises(NotFoundError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1])
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_naming_one_missing_holding_refuses_the_whole_move(self, monkeypatch):
        # A partial move is the worst outcome available: the caller is told nothing failed while some
        # of what they named stayed where it was.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.investment_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._investment(1)]))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        with pytest.raises(NotFoundError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1, 999])
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_account_with_linked_entries_cannot_be_shared(self, monkeypatch):
        # Its balance derives from rows owned by ONE user, so a shared version would report a
        # different figure to every member depending on whose rows they can see.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.account_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._account(7)]))
        _no_movements(monkeypatch)
        monkeypatch.setattr(pot_service.transfer_repository, "linked_account_ids", AsyncMock(return_value={7}))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        with pytest.raises(AccountHasLinkedEntriesError) as excinfo:
            await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7])
        assert excinfo.value.extra == {"account_ids": [7]}
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_account_with_ownership_history_cannot_be_shared_either(self, monkeypatch):
        # An ownership event names a private account on one leg and a pot account on the other, so
        # moving the private one in would leave a movement whose two ends sit in the same scope —
        # money that left the pot and arrived back in it. The four linked_account_ids checks do not
        # cover this: an ownership event is none of income, expense, settlement or transfer.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.account_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._account(7)]))
        _no_movements(monkeypatch)
        monkeypatch.setattr(pot_service.pot_ownership_repository, "linked_account_ids", AsyncMock(return_value={7}))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        with pytest.raises(AccountHasLinkedEntriesError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7])
        move.assert_not_awaited()

    @pytest.mark.parametrize(
        "repository",
        ["shared_expense_repository", "shared_income_repository", "group_settlement_repository"],
    )
    @pytest.mark.asyncio
    async def test_an_account_carrying_a_GROUP_row_cannot_be_shared(self, monkeypatch, repository):
        # The blind spot the four private checks cannot see: they all filter by user_id, and a group's
        # row belongs to no user. So an account whose only history is shared — a distributed income's
        # destination, a shared expense's funding account, a settlement's cash leg — passed every one
        # of them and moved into the pot, where the whole of that money then raised every owner's share
        # pro-rata while the splits still said the collector owed each of them their share. The same
        # money counted twice, and the row left unsaveable because its account no longer had an owner.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.account_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._account(7)]))
        _no_movements(monkeypatch)
        monkeypatch.setattr(getattr(pot_service, repository), "linked_account_ids", AsyncMock(return_value={7}))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        with pytest.raises(AccountHasLinkedEntriesError) as excinfo:
            await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7])
        assert excinfo.value.extra == {"account_ids": [7]}
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_clean_account_moves_in(self, monkeypatch):
        # The positive control for both guards: without it, "raises" above would pass even if the
        # method refused every account unconditionally.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.account_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._account(7)]))
        _no_movements(monkeypatch)
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", AsyncMock(return_value=0))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7])
        assert move.await_args.kwargs == {"pot_id": 5, "user_id": None}

    @pytest.mark.asyncio
    async def test_moving_out_takes_the_holding_back_to_the_caller_as_private(self, monkeypatch):
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pot_service.investment_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._investment(1, user_id=None, pot_id=5)])
        )
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", AsyncMock(return_value=0))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1], into=False)
        assert move.await_args.kwargs == {"pot_id": None, "user_id": USER.id}

    @pytest.mark.asyncio
    async def test_a_holding_cannot_LEAVE_a_pot_whose_ownership_is_already_agreed(self, monkeypatch):
        # The most serious hole this PR had: an unguarded move-out drops the pot's value by the whole
        # holding while nobody's units change, so every co-owner's share falls pro-rata and the
        # holding lands wholly in one person's private scope. One member taking joint assets, with no
        # cap — strictly worse than the private-expense case O1 refuses.
        from app.domain import PotAlreadyDividedError

        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[object()]))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        with pytest.raises(PotAlreadyDividedError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1], into=False)
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_holding_CAN_leave_a_pot_that_has_not_been_divided_yet(self, monkeypatch):
        # The positive control, and the case that matters in practice: undoing a mistaken move-in
        # before the baseline exists takes nothing from anybody, because nothing has been divided.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pot_service.investment_repository,
            "get_by_ids_any_scope",
            AsyncMock(return_value=[self._investment(1, user_id=None, pot_id=5)]),
        )
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", AsyncMock(return_value=0))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1], into=False)
        assert move.await_args.kwargs == {"pot_id": None, "user_id": USER.id}

    @pytest.mark.asyncio
    async def test_moving_IN_is_refused_once_the_pot_is_divided_too(self, monkeypatch):
        # The mirror of the move-out refusal, and it is refused for the OPPOSITE reason: adding a
        # holding raises the pot's value with nobody's units changing, so value that came wholly out of
        # one person's private scope is handed to every owner pro-rata — a gift, made silently.
        # A distinct code, because the remedy differs: taking out is a withdrawal, putting in is a
        # contribution, and one message cannot name both.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[object()]))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        with pytest.raises(PotHoldingAddDividedError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1], into=True)
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_moving_IN_is_free_while_nothing_has_been_divided(self, monkeypatch):
        # An empty ledger means nothing has been agreed, so neither direction takes anything from
        # anyone — which is also what keeps "undo a mistaken move-in" possible.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.investment_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._investment(1)]))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", AsyncMock(return_value=0))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1], into=True)
        assert move.await_args.kwargs == {"pot_id": 5, "user_id": None}

    @pytest.mark.asyncio
    async def test_an_account_carrying_a_pot_scoped_transfer_cannot_LEAVE_the_pot(self, monkeypatch):
        # The mirror image of the move-in guard, and the reason it needed its own check: a transfer
        # between two pot accounts is pot-scoped, so linked_account_ids — which filters by user_id —
        # is structurally blind to it. Without the scope-free probe this move would succeed and leave
        # the transfer with one leg in each scope, which no transfer may have, while the balance union
        # silently stopped counting it against the account that just went private.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pot_service.account_repository,
            "get_by_ids_any_scope",
            AsyncMock(return_value=[self._account(7, user_id=None, pot_id=5)]),
        )
        _no_movements(monkeypatch)
        monkeypatch.setattr(pot_service.transfer_repository, "linked_account_ids_any_scope", AsyncMock(return_value={7}))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        with pytest.raises(AccountHasLinkedEntriesError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7], into=False)
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_clean_account_can_leave_the_pot(self, monkeypatch):
        # The positive control for the guard above.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pot_service.account_repository,
            "get_by_ids_any_scope",
            AsyncMock(return_value=[self._account(7, user_id=None, pot_id=5)]),
        )
        _no_movements(monkeypatch)
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", AsyncMock(return_value=0))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7], into=False)
        assert move.await_args.kwargs == {"pot_id": None, "user_id": USER.id}

    @pytest.mark.asyncio
    async def test_a_holding_from_another_pot_cannot_be_pulled_out(self, monkeypatch):
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            pot_service.investment_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._investment(1, user_id=None, pot_id=99)])
        )
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", move)
        with pytest.raises(NotFoundError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, investment_ids=[1], into=False)
        move.assert_not_awaited()


class TestContributionRefusal:
    # THE rule the picker filters on and the write raises. Every case below is a row that must not be
    # offered, because a row that is offered and then 400s is exactly what U6 forbids.

    PRICE = Decimal("1.10")

    @staticmethod
    def _row(value, base_value, currency="USD"):
        return PotHoldingResponse(id=1, name="X", currency=currency, value=value, base_value=base_value, is_active=True, valued_on=None)

    def test_a_valued_positive_convertible_holding_is_contributable(self):
        # The positive control. Without it every assertion below passes on a rule that refuses
        # everything.
        assert pot_service.contribution_refusal(self._row(Decimal("55"), Decimal("55")), "USD", self.PRICE) is None

    def test_a_holding_nobody_has_valued_is_refused_for_being_unvalued(self):
        # An investment with no snapshot on or before today. The units issued ARE its value, so there
        # is nothing to issue — and treating it as zero would take an asset and give nothing back.
        refusal = pot_service.contribution_refusal(self._row(None, None), "USD", self.PRICE)
        assert isinstance(refusal, PotHoldingUnvaluedError)

    def test_an_emptied_or_overdrawn_account_is_refused_for_being_worth_nothing(self):
        # Zero issues no units; a negative would REDEEM units the contributor may not even hold — a
        # withdrawal wearing a contribution's name.
        #
        # ACROSS CURRENCIES on purpose. A non-positive figure converts to a non-positive one, so the
        # units test further down refuses the same rows — and against a same-currency fixture the two
        # name the identical figure, which is how a mutation deleting this check stayed green. What the
        # check actually buys is the figure the PERSON recognises: -10 ARS, not -0.01 USD.
        for value, base in ((Decimal("0"), Decimal("0.00")), (Decimal("-10"), Decimal("-0.01"))):
            refusal = pot_service.contribution_refusal(self._row(value, base, currency="ARS"), "USD", self.PRICE)
            assert isinstance(refusal, PotHoldingNotPositiveError)
            assert refusal.extra == {"value": str(value), "currency": "ARS"}

    def test_a_holding_whose_currency_has_no_rate_is_refused_naming_the_pots_currency(self):
        # A real value, no way to state it in the pot's currency. Distinct from unvalued because the
        # remedy is distinct: a rate, not a snapshot.
        refusal = pot_service.contribution_refusal(self._row(Decimal("66000"), None, currency="ARS"), "USD", self.PRICE)
        assert isinstance(refusal, ExchangeRateUnavailableError)
        assert refusal.extra == {"currency": "USD"}

    def test_a_holding_worth_nothing_ONCE_CONVERTED_is_refused_in_the_pots_currency(self):
        # The quiet one: genuinely positive in its own currency, and 0.00 in the pot's. The refusal
        # names the base figure and the base currency, because that is the figure that is the problem.
        refusal = pot_service.contribution_refusal(self._row(Decimal("1"), Decimal("0.00"), currency="ARS"), "USD", self.PRICE)
        assert isinstance(refusal, PotHoldingNotPositiveError)
        assert refusal.extra == {"value": "0.00", "currency": "USD"}

    def test_a_holding_too_small_to_buy_a_millionth_of_a_unit_is_refused(self):
        # Positive both ways and still worth nothing HERE, because units are NUMERIC(18,6): at a unit
        # price of 100,000 a base figure of 0.01 divides to 0.0000001, which rounds to zero units. The
        # asset would move and nothing would be issued for it. Reachable only on a pot that has grown
        # enormously, which is why the guard is stated rather than left to arithmetic nobody checked.
        refusal = pot_service.contribution_refusal(self._row(Decimal("0.01"), Decimal("0.01")), "USD", Decimal("100000"))
        assert isinstance(refusal, PotHoldingNotPositiveError)


class TestResolvingAContributableHolding:
    # Which of the caller's own things may be handed to a pot, and what each refusal protects.

    @staticmethod
    def _investment(**kwargs) -> Investment:
        defaults = dict(id=12, user_id=USER.id, pot_id=None, name="Fondo", category=InvestmentCategory.fci, base_currency="USD", is_active=True)
        return Investment(**{**defaults, **kwargs})

    @pytest.mark.asyncio
    async def test_the_callers_own_private_active_investment_resolves(self, monkeypatch):
        investment = self._investment()
        monkeypatch.setattr(pot_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=investment))
        assert await pot_service.require_contributable_holding(AsyncMock(), USER, investment_id=12, account_id=None) is investment

    @pytest.mark.asyncio
    async def test_somebody_elses_holding_is_a_404_rather_than_a_refusal(self, monkeypatch):
        # Belt and braces over RLS, and deliberately indistinguishable from "no such id": a specific
        # refusal here would confirm that somebody else's investment exists.
        monkeypatch.setattr(pot_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=self._investment(user_id=OTHER.id)))
        with pytest.raises(NotFoundError):
            await pot_service.require_contributable_holding(AsyncMock(), USER, investment_id=12, account_id=None)

    @pytest.mark.asyncio
    async def test_a_holding_already_inside_a_pot_is_a_404_too(self, monkeypatch):
        # Contributing a pot's own holding back to it would issue units for value that pot already
        # counts, and contributing ANOTHER pot's would move it sideways out of its owners' hands.
        monkeypatch.setattr(
            pot_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=self._investment(user_id=None, pot_id=7))
        )
        with pytest.raises(NotFoundError):
            await pot_service.require_contributable_holding(AsyncMock(), USER, investment_id=12, account_id=None)

    @pytest.mark.asyncio
    async def test_a_row_naming_BOTH_an_owner_and_a_pot_is_refused_too(self, monkeypatch):
        # The state investments_single_owner makes impossible in the database, constructed here because
        # that is the only place it can exist. Without this the pot_id clause is unreachable — a shared
        # holding has user_id NULL, so the owner check alone already refuses every real row, and a
        # mutation deleting the clause stayed green. Refusing it keeps the service fail-closed if the
        # constraint is ever dropped or a row drifts.
        monkeypatch.setattr(pot_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=self._investment(pot_id=7)))
        with pytest.raises(NotFoundError):
            await pot_service.require_contributable_holding(AsyncMock(), USER, investment_id=12, account_id=None)

    @pytest.mark.asyncio
    async def test_an_archived_holding_is_refused_by_name(self, monkeypatch):
        # Both NAV queries filter on is_active, so an archived holding raises nobody's value — units
        # issued against it would dilute every other owner for nothing. A real refusal rather than a
        # 404, because the caller can act on it: restore it.
        monkeypatch.setattr(pot_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=self._investment(is_active=False)))
        with pytest.raises(PotHoldingInactiveError):
            await pot_service.require_contributable_holding(AsyncMock(), USER, investment_id=12, account_id=None)

    @pytest.mark.asyncio
    async def test_an_account_carrying_movements_cannot_be_contributed_either(self, monkeypatch):
        # The same rule and the same enumeration the plain move applies: a shared account whose balance
        # derives from one person's rows reports a different figure to every member.
        account = Account(id=7, user_id=USER.id, name="A", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        monkeypatch.setattr(pot_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=account))
        _no_movements(monkeypatch)
        monkeypatch.setattr(pot_service.expense_repository, "linked_account_ids", AsyncMock(return_value={7}))
        with pytest.raises(AccountHasLinkedEntriesError):
            await pot_service.require_contributable_holding(AsyncMock(), USER, account_id=7, investment_id=None)

    @pytest.mark.asyncio
    async def test_a_clean_account_resolves(self, monkeypatch):
        account = Account(id=7, user_id=USER.id, name="A", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        monkeypatch.setattr(pot_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=account))
        _no_movements(monkeypatch)
        assert await pot_service.require_contributable_holding(AsyncMock(), USER, account_id=7, investment_id=None) is account


class TestAttachingTheHolding:
    # Which table the move actually writes to. An investment and an account are re-pointed by different
    # repositories, and both calls look identical at the call site — so a branch that always took the
    # investment path moved nothing when an ACCOUNT was contributed, leaving a ledger entry issuing
    # units against a holding that never arrived. A mutation proved nothing caught that.

    @staticmethod
    def _wire(monkeypatch):
        investment = AsyncMock(return_value=1)
        account = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", investment)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", account)
        return (investment, account)

    @pytest.mark.asyncio
    async def test_an_investment_is_re_pointed_by_the_investment_repository(self, monkeypatch):
        investment, account = self._wire(monkeypatch)
        row = Investment(id=12, user_id=USER.id, name="Fondo", category=InvestmentCategory.fci, base_currency="USD")
        await pot_service.attach_holding(AsyncMock(), _pot(), row)
        assert investment.await_args.args[1] == [12]
        assert investment.await_args.kwargs == {"pot_id": 5, "user_id": None}
        account.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_account_is_re_pointed_by_the_account_repository(self, monkeypatch):
        investment, account = self._wire(monkeypatch)
        row = Account(id=7, user_id=USER.id, name="A", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        await pot_service.attach_holding(AsyncMock(), _pot(), row)
        assert account.await_args.args[1] == [7]
        assert account.await_args.kwargs == {"pot_id": 5, "user_id": None}
        investment.assert_not_awaited()


class TestTheContributionPicker:
    # The picker offers exactly what the write accepts. Asserted as an AGREEMENT between the two rather
    # than as a list of expected rows: a per-row expectation agrees with itself forever, while running
    # both sides over one set of candidates fails the moment either drifts.

    @staticmethod
    def _wire(monkeypatch, *, investments, snapshots, accounts=(), balances=None, linked=frozenset(), nav=Decimal("110")):
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=_LOOKUP))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[_opening_event()]))
        monkeypatch.setattr(pot_service, "get_valuation", AsyncMock(return_value=PotValuation(nav=nav, valued_as_of=None, is_stale=False)))
        monkeypatch.setattr(pot_service.metrics_repository, "list_active_investments", AsyncMock(return_value=list(investments)))
        monkeypatch.setattr(pot_service.account_repository, "list_by_user", AsyncMock(return_value=list(accounts)))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value=snapshots))
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value=balances or {}))
        monkeypatch.setattr(pot_service, "_accounts_with_movements", AsyncMock(return_value=set(linked)))

    @pytest.mark.asyncio
    async def test_it_offers_the_valued_ones_and_drops_the_rest(self, monkeypatch):
        # Three investments, one of each state, so the drop is visible against a control that stays.
        valued = Investment(id=1, user_id=USER.id, name="Fondo", category=InvestmentCategory.fci, base_currency="USD")
        unvalued = Investment(id=2, user_id=USER.id, name="Nuevo", category=InvestmentCategory.fci, base_currency="USD")
        empty = Investment(id=3, user_id=USER.id, name="Vacio", category=InvestmentCategory.fci, base_currency="USD")
        snapshots = {
            1: InvestmentSnapshot(investment_id=1, date=date(2026, 2, 1), value=Decimal("55"), currency="USD"),
            3: InvestmentSnapshot(investment_id=3, date=date(2026, 2, 1), value=Decimal("0"), currency="USD"),
        }
        self._wire(monkeypatch, investments=[valued, unvalued, empty], snapshots=snapshots)
        offered = await pot_service.list_contributable_holdings(AsyncMock(), 5, USER)
        assert [row.id for row in offered.investments] == [1]
        assert offered.investments[0].value == Decimal("55")

    @pytest.mark.asyncio
    async def test_an_account_carrying_movements_is_not_offered(self, monkeypatch):
        clean = Account(id=7, user_id=USER.id, name="Clean", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        dirty = Account(id=8, user_id=USER.id, name="Dirty", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        self._wire(
            monkeypatch,
            investments=[],
            snapshots={},
            accounts=[clean, dirty],
            balances={7: Decimal("500"), 8: Decimal("500")},
            linked={8},
        )
        offered = await pot_service.list_contributable_holdings(AsyncMock(), 5, USER)
        assert [row.id for row in offered.accounts] == [7]

    @pytest.mark.asyncio
    async def test_every_offered_row_is_one_the_write_would_accept(self, monkeypatch):
        # The agreement itself, over a candidate set holding one of every state. The picker's answer
        # and the write's answer are read from the SAME rule, so this fails the moment either side
        # grows a condition the other does not have.
        rows = [
            Investment(id=1, user_id=USER.id, name="Fondo", category=InvestmentCategory.fci, base_currency="USD"),
            Investment(id=2, user_id=USER.id, name="Nuevo", category=InvestmentCategory.fci, base_currency="USD"),
            Investment(id=3, user_id=USER.id, name="Vacio", category=InvestmentCategory.fci, base_currency="USD"),
        ]
        snapshots = {
            1: InvestmentSnapshot(investment_id=1, date=date(2026, 2, 1), value=Decimal("55"), currency="USD"),
            3: InvestmentSnapshot(investment_id=3, date=date(2026, 2, 1), value=Decimal("-5"), currency="USD"),
        }
        self._wire(monkeypatch, investments=rows, snapshots=snapshots)
        offered = await pot_service.list_contributable_holdings(AsyncMock(), 5, USER)
        offered_ids = {row.id for row in offered.investments}

        pot = _pot()
        price = Decimal("1.10")
        for investment in rows:
            valued = pot_service._investment_holding(investment, snapshots.get(investment.id), pot=pot, rate_map={})
            accepted = pot_service.contribution_refusal(valued, pot.base_currency, price) is None
            assert (investment.id in offered_ids) is accepted, f"picker and write disagree about {investment.name}"

    @pytest.mark.asyncio
    async def test_a_pot_with_no_price_offers_nothing_at_all(self, monkeypatch):
        # With no usable valuation the write refuses every row for that reason first, so listing
        # candidates would be a page of rows that all 400. The flow's own gate keeps this unreachable;
        # the endpoint stays honest on its own.
        valued = Investment(id=1, user_id=USER.id, name="Fondo", category=InvestmentCategory.fci, base_currency="USD")
        self._wire(
            monkeypatch,
            investments=[valued],
            snapshots={1: InvestmentSnapshot(investment_id=1, date=date(2026, 2, 1), value=Decimal("55"), currency="USD")},
            nav=None,
        )
        offered = await pot_service.list_contributable_holdings(AsyncMock(), 5, USER)
        assert (offered.investments, offered.accounts) == ([], [])


class TestAbsorbingPotsOnAccountDeletion:
    @pytest.mark.asyncio
    async def test_every_holding_in_an_orphaned_groups_pots_is_reassigned(self, monkeypatch):
        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", AsyncMock(return_value=[_pot(id=5), _pot(id=6)]))
        investments = AsyncMock(return_value=4)
        accounts = AsyncMock(return_value=2)
        monkeypatch.setattr(pot_service.investment_repository, "reassign_pots_to_user", investments)
        monkeypatch.setattr(pot_service.account_repository, "reassign_pots_to_user", accounts)
        moved = await pot_service.absorb_group_pots(AsyncMock(), [10], USER.id)
        assert moved == 6
        # Two statements for the whole set, not two per pot: the cost of deleting an account must not
        # grow with how much the leaver happened to share.
        assert (investments.await_count, accounts.await_count) == (1, 1)
        assert investments.await_args.args[1:] == ([5, 6], USER.id)

    @pytest.mark.asyncio
    async def test_no_orphaned_groups_touches_nothing(self, monkeypatch):
        list_by_group = AsyncMock(return_value=[])
        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", list_by_group)
        assert await pot_service.absorb_group_pots(AsyncMock(), [], USER.id) == 0
        list_by_group.assert_not_awaited()


class TestOneMembersShare:
    # What the dashboard reads per pot: the member's own share, and what the pot's value is made of.
    def _wire(self, monkeypatch, *, investments, snapshots, accounts=(), balances=None):
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=list(investments)))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value=dict(snapshots)))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=list(accounts)))
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value=dict(balances or {})))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        return lookup

    def _seat(self, events=()):
        return pot_service.PotSeat(pot=_pot(base_currency="USD"), member_id=SEAT.id, events=list(events))

    def _opening(self, member_id: int, on: date, units: str):
        from app.models.pot import OwnershipEventType, PotOwnershipEvent

        return PotOwnershipEvent(
            id=None, pot_id=5, type=OwnershipEventType.opening, date=on, member_id=member_id, units=Decimal(units), unit_price=Decimal(1)
        )

    @pytest.mark.asyncio
    async def test_each_holding_is_labelled_with_the_bucket_it_contributes_to(self, monkeypatch):
        # The composition folds a member's share into the same segments a private holding lands in, so
        # a co-owned CEDEAR has to arrive labelled `cedears` and a jointly held account labelled `cash`.
        # A mutation that labelled every investment `cash` was invisible to every other test.
        cedear = Investment(id=1, user_id=None, pot_id=5, name="AAPL", category=InvestmentCategory.cedears, base_currency="USD")
        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 6, 1), value=Decimal("300"), currency="USD")
        account = Account(id=9, user_id=None, pot_id=5, name="Joint", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        lookup = self._wire(monkeypatch, investments=[cedear], snapshots={1: snapshot}, accounts=[account], balances={9: Decimal("100")})

        share = await pot_service.get_member_share(
            AsyncMock(), self._seat([self._opening(SEAT.id, date(2026, 2, 1), "100")]), as_of_date=date(2026, 7, 1), lookup=lookup
        )
        assert share.nav == Decimal("400")
        assert share.weights == {"cedears": Decimal("300"), "cash": Decimal("100")}
        assert share.value == Decimal("400")

    @pytest.mark.asyncio
    async def test_an_event_AFTER_the_date_asked_about_does_not_count(self, monkeypatch):
        # The ledger is bounded in Python because the batch read fetched every pot's events at once.
        # Without the bound a past valuation would be divided by a division agreed afterwards.
        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("100"), currency="USD")
        investment = Investment(id=1, user_id=None, pot_id=5, name="F", category=InvestmentCategory.fci, base_currency="USD")
        lookup = self._wire(monkeypatch, investments=[investment], snapshots={1: snapshot})
        events = [self._opening(SEAT.id, date(2026, 2, 1), "50"), self._opening(PLAIN_SEAT.id, date(2026, 9, 1), "50")]

        # In March only the first opening has happened, so the whole pot is this member's.
        march = await pot_service.get_member_share(AsyncMock(), self._seat(events), as_of_date=date(2026, 3, 1), lookup=lookup)
        assert march.value == Decimal("100")
        # By October the second owner holds half of it.
        october = await pot_service.get_member_share(AsyncMock(), self._seat(events), as_of_date=date(2026, 10, 1), lookup=lookup)
        assert october.value == Decimal("50")

    @pytest.mark.asyncio
    async def test_an_undivided_pot_has_no_share_to_state(self, monkeypatch):
        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("100"), currency="USD")
        investment = Investment(id=1, user_id=None, pot_id=5, name="F", category=InvestmentCategory.fci, base_currency="USD")
        lookup = self._wire(monkeypatch, investments=[investment], snapshots={1: snapshot})
        share = await pot_service.get_member_share(AsyncMock(), self._seat(), as_of_date=date(2026, 3, 1), lookup=lookup)
        assert share.nav == Decimal("100")
        assert share.value is None
        assert share.holds_anything is True


class TestNav:
    @pytest.mark.asyncio
    async def test_an_unconvertible_holding_makes_the_nav_unknown_rather_than_understated(self, monkeypatch):
        # Fail-loud, and it matters more here than anywhere else: an understated NAV would silently
        # misprice every unit issued against it.
        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("100"), currency="BRL")
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: snapshot}))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) is None

    @pytest.mark.asyncio
    async def test_the_valuation_date_is_pushed_DOWN_into_the_snapshot_query(self, monkeypatch):
        # Not filtered in the service after the fact, which is the bug this replaced: taking each
        # investment's latest snapshot and then discarding it for being too new DROPS the investment
        # entirely, when what was asked for is its value on that date. Bounding the query's MAX
        # returns the latest snapshot on or before it instead. Asserted on the argument the service
        # passed, because a stub returns whatever it was told either way.
        latest = AsyncMock(return_value={})
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", latest)
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup)
        assert latest.await_args.kwargs == {"as_of_date": date(2026, 6, 1)}

    @pytest.mark.asyncio
    async def test_a_pot_whose_holdings_have_no_snapshot_by_that_date_has_an_UNKNOWN_value(self, monkeypatch):
        # Not zero. A pot holding something nobody has valued is not worth nothing, and reporting zero
        # tells every co-owner their money is gone.
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={}))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) is None

    @pytest.mark.asyncio
    async def test_ONE_unvalued_holding_makes_the_whole_nav_unknown(self, monkeypatch):
        """The defect this replaced, and the worst of them: two holdings, one snapshotted, and the sum
        came back as the valued one's figure alone. Complete-looking, incomplete, and a contribution
        priced against it issues units against a value that is not the pot's — real value moving
        between owners from a movement that looks ordinary. Same failure as a wrongly bounded snapshot
        query, reached from the other direction."""
        from app.models.snapshot import InvestmentSnapshot as Snapshot

        snapshot = Snapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("100"), currency="USD")
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1), _pot_investment(2)]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: snapshot}))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) is None

    @pytest.mark.asyncio
    async def test_a_pot_holding_nothing_at_all_has_an_unknown_value_rather_than_zero(self, monkeypatch):
        # A NAV is a valuation OF something. Null is also what PotResponse documents for this case, and
        # a pot cannot be valued at <= 0 for ownership purposes anyway.
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) is None

    @pytest.mark.asyncio
    async def test_a_fully_valued_pot_sums_to_its_holdings(self, monkeypatch):
        # The positive control. Without it, "return None" for every input passes every test above.
        from app.models.snapshot import InvestmentSnapshot as Snapshot

        snapshots = {
            1: Snapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("100"), currency="USD"),
            2: Snapshot(id=2, investment_id=2, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("10.50"), currency="USD"),
        }
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1), _pot_investment(2)]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value=snapshots))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) == Decimal("110.50")

    @pytest.mark.asyncio
    async def test_an_account_only_pot_is_valued_at_its_balance(self, monkeypatch):
        # Accounts have no unvalued case — an account always has a balance, its opening figure at worst
        # — so the completeness rule above must not accidentally require a snapshot for them.
        account = Account(id=9, user_id=None, pot_id=5, name="Conjunta", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[account]))
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value={9: Decimal("42.00")}))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) == Decimal("42.00")


class TestHoldings:
    def _investment(self, id: int, name: str, *, currency: str = "USD", is_active: bool = True) -> Investment:
        return Investment(id=id, user_id=None, pot_id=5, name=name, category=InvestmentCategory.fci, base_currency=currency, is_active=is_active)

    def _account(self, id: int, name: str, *, currency: str = "USD", is_active: bool = True) -> Account:
        return Account(
            id=id, user_id=None, pot_id=5, name=name, type=AccountType.bank, currency=currency, opening_date=date(2026, 1, 1), is_active=is_active
        )

    def _snapshot(self, investment_id: int, value: str, currency: str) -> InvestmentSnapshot:
        return InvestmentSnapshot(
            id=investment_id, investment_id=investment_id, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal(value), currency=currency
        )

    # Stubs everything list_holdings reaches except the visibility gate, so each test below varies one
    # thing. `rates` is the rate map the conversion sees; an empty one converts nothing.
    def _wire(self, monkeypatch, *, investments=(), accounts=(), snapshots=None, balances=None, rates=None):
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot()))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=_permission(can_view=True)))
        monkeypatch.setattr(pot_service.pot_repository, "list_holdings", AsyncMock(return_value=(list(investments), list(accounts))))
        latest = AsyncMock(return_value=snapshots or {})
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", latest)
        compute = AsyncMock(return_value=balances or {})
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", compute)
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)} if rates is None else rates
        monkeypatch.setattr(pot_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))
        return (latest, compute)

    @pytest.mark.asyncio
    async def test_a_read_only_member_owning_none_of_it_sees_every_holding(self, monkeypatch):
        # V5: whoever may see a pot sees it in full. The gate is require_visible, NOT require_writable
        # — reading the monitoring surface is not a write, and gating it on write access would hide the
        # pot from exactly the custodian-and-observers arrangement V6 exists for.
        self._wire(
            monkeypatch,
            investments=[self._investment(1, "Fondo")],
            snapshots={1: self._snapshot(1, "100.00", "USD")},
        )
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=_permission(can_view=True, can_write=False)))
        holdings = await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert [(h.name, h.value) for h in holdings.investments] == [("Fondo", Decimal("100.00"))]

    @pytest.mark.asyncio
    async def test_a_pot_the_caller_may_not_see_answers_404_rather_than_an_empty_list(self, monkeypatch):
        self._wire(monkeypatch)
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=_pot(visibility=PotVisibility.owners)))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await pot_service.list_holdings(AsyncMock(), 5, USER)

    @pytest.mark.asyncio
    async def test_an_investment_nobody_has_valued_yet_is_listed_with_no_figure_at_all(self, monkeypatch):
        # Null both ways, not zero. A pot can legitimately hold something with no snapshot, and "worth
        # nothing" is a claim the ledger has not made — the same distinction nav and unit_price draw.
        self._wire(monkeypatch, investments=[self._investment(1, "Fondo")], snapshots={})
        holdings = await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert (holdings.investments[0].value, holdings.investments[0].base_value) == (None, None)

    @pytest.mark.asyncio
    async def test_one_unconvertible_holding_loses_only_its_own_base_figure(self, monkeypatch):
        # Deliberately UNLIKE get_nav, which abandons the whole sum: an under-stated NAV misprices
        # every unit issued against it, whereas a list that dropped a holding would hide something the
        # pot demonstrably holds. Both figures still say what they know.
        self._wire(
            monkeypatch,
            investments=[self._investment(1, "Local", currency="USD"), self._investment(2, "Brasil", currency="BRL")],
            snapshots={1: self._snapshot(1, "100.00", "USD"), 2: self._snapshot(2, "500.00", "BRL")},
            rates={},
        )
        holdings = await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert [(h.name, h.value, h.base_value) for h in holdings.investments] == [
            ("Local", Decimal("100.00"), Decimal("100.00")),
            ("Brasil", Decimal("500.00"), None),
        ]

    @pytest.mark.asyncio
    async def test_the_figure_is_read_in_the_snapshots_currency_not_the_investments(self, monkeypatch):
        # The NAV converts from the SNAPSHOT's currency column, so this must too or the two could
        # disagree about which currency one figure is in. They are enforced equal on write, which is
        # not the same as being one column.
        self._wire(
            monkeypatch,
            investments=[self._investment(1, "Fondo", currency="USD")],
            snapshots={1: self._snapshot(1, "500.00", "BRL")},
            rates={},
        )
        holdings = await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert (holdings.investments[0].currency, holdings.investments[0].base_value) == ("BRL", None)

    @pytest.mark.asyncio
    async def test_an_unvalued_investment_still_names_the_currency_it_would_be_in(self, monkeypatch):
        # The fallback half of the rule above: with no snapshot there is no currency column to read,
        # so the investment's own is what the row reports.
        self._wire(monkeypatch, investments=[self._investment(1, "Fondo", currency="BRL")], snapshots={})
        assert (await pot_service.list_holdings(AsyncMock(), 5, USER)).investments[0].currency == "BRL"

    @pytest.mark.asyncio
    async def test_an_account_with_no_computed_row_reads_zero_rather_than_unknown(self, monkeypatch):
        # An account always has a balance — its opening figure at worst — so unlike an investment it is
        # never unvalued, and a missing key means zero rather than "we do not know".
        self._wire(monkeypatch, accounts=[self._account(9, "Conjunta")], balances={})
        holdings = await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert (holdings.accounts[0].value, holdings.accounts[0].base_value) == (Decimal(0), Decimal(0))

    @pytest.mark.asyncio
    async def test_an_archived_holding_is_listed_and_flagged(self, monkeypatch):
        # It still points at the pot, so it still blocks deleting the pot and still has to be movable
        # back out. Whether the QUERY returns it is asserted against a real database — a stub returns
        # whatever it was told — so what this pins is that the flag reaches the response.
        self._wire(
            monkeypatch,
            investments=[self._investment(1, "Vieja", is_active=False)],
            accounts=[self._account(9, "Cerrada", is_active=False)],
            snapshots={1: self._snapshot(1, "100.00", "USD")},
            balances={9: Decimal("50.00")},
        )
        holdings = await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert (holdings.investments[0].is_active, holdings.accounts[0].is_active) == (False, False)

    @pytest.mark.asyncio
    async def test_todays_date_bounds_the_snapshot_query(self, monkeypatch):
        # Asserted on the argument the service PASSED, not on what the stub returned. Without the
        # bound the list would show a value the pot's NAV does not count.
        latest, _ = self._wire(monkeypatch, investments=[self._investment(1, "Fondo")])
        await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert latest.await_args.kwargs == {"as_of_date": date.today()}

    @pytest.mark.asyncio
    async def test_both_lookups_are_batched_however_much_the_pot_holds(self, monkeypatch):
        # One snapshot query and one balance query for the whole pot, so a pot holding twenty things
        # costs what one holding two does.
        latest, compute = self._wire(
            monkeypatch,
            investments=[self._investment(i, f"F{i}") for i in (1, 2, 3)],
            accounts=[self._account(i, f"A{i}") for i in (7, 8)],
        )
        await pot_service.list_holdings(AsyncMock(), 5, USER)
        assert (latest.await_count, compute.await_count) == (1, 1)
        assert latest.await_args.args[1] == [1, 2, 3]


class TestValuationFreshness:
    # `valued_as_of` answers a different question from `nav`, and the two are allowed to disagree.
    # These name the rule rather than the function, because each one is a sentence a member reads on
    # the pot page ("as of 3 June", "never valued", "needs an update").

    def _snapshot(self, investment_id: int, on: date, *, currency: str = "USD") -> InvestmentSnapshot:
        return InvestmentSnapshot(
            id=investment_id, investment_id=investment_id, user_id=None, pot_id=5, date=on, value=Decimal("100"), currency=currency
        )

    def _lookup(self, rates=None):
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)} if rates is None else rates
        return lookup

    def _account(self, *, currency: str = "USD") -> Account:
        return Account(id=1, user_id=None, pot_id=5, name="Joint", type=AccountType.bank, currency=currency, opening_date=date(2026, 1, 1))

    @pytest.mark.asyncio
    async def test_a_pot_is_current_only_to_its_STALEST_holding(self, monkeypatch):
        # The whole rule in one test: a total is only as current as the oldest term in it. One holding
        # nobody has touched since March makes the pot a March figure however fresh the rest are, and
        # reporting the newest date instead would call a half-stale pot up to date.
        snapshots = {1: self._snapshot(1, date(2026, 3, 2)), 2: self._snapshot(2, date(2026, 6, 1))}
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1), _pot_investment(2)]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value=snapshots))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup())
        assert valuation.valued_as_of == date(2026, 3, 2)
        assert valuation.is_stale is True

    @pytest.mark.asyncio
    async def test_a_holding_nobody_has_ever_valued_leaves_no_date_to_state(self, monkeypatch):
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1), _pot_investment(2)]))
        monkeypatch.setattr(
            pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: self._snapshot(1, date(2026, 6, 1))})
        )
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup())
        assert (valuation.nav, valuation.valued_as_of, valuation.is_stale) == (None, None, True)

    @pytest.mark.asyncio
    async def test_an_account_only_pot_is_current_by_construction(self, monkeypatch):
        # An account's balance is DERIVED at the date asked for, so there is nothing to be behind on
        # and no cadence can make it overdue.
        account = Account(id=9, user_id=None, pot_id=5, name="Conjunta", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[account]))
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value={9: Decimal("42.00")}))
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup())
        assert (valuation.valued_as_of, valuation.is_stale) == (date(2026, 6, 15), False)

    @pytest.mark.asyncio
    async def test_an_account_does_not_drag_a_stale_investment_forward(self, monkeypatch):
        # The mirror of the test above, and the one a naive "accounts are current, so the pot is
        # current" reading gets wrong: an account alongside a stale investment must not make the pot
        # read fresh, because the NAV still contains the stale term.
        account = Account(id=9, user_id=None, pot_id=5, name="Conjunta", type=AccountType.bank, currency="USD", opening_date=date(2026, 1, 1))
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(
            pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: self._snapshot(1, date(2026, 1, 5))})
        )
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[account]))
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", AsyncMock(return_value={9: Decimal("42.00")}))
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup())
        assert (valuation.valued_as_of, valuation.is_stale) == (date(2026, 1, 5), True)

    @pytest.mark.asyncio
    async def test_an_unconvertible_pot_still_says_when_it_was_last_valued(self, monkeypatch):
        # Two different problems, two different fields. The snapshots are fresh; this currency just
        # cannot state them, so collapsing both into "unknown" would hide a fact the page has.
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(
            pot_service.snapshot_repository,
            "get_latest_by_investments",
            AsyncMock(return_value={1: self._snapshot(1, date(2026, 6, 10), currency="BRL")}),
        )
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup(rates={}))
        assert (valuation.nav, valuation.valued_as_of, valuation.is_stale) == (None, date(2026, 6, 10), False)

    @pytest.mark.asyncio
    async def test_an_unconvertible_investment_still_costs_no_balance_query(self, monkeypatch):
        # The ordering the two sums have always had: abandoning the total must not go on to pay for a
        # balance union whose result cannot be used.
        #
        # Asserted on `compute_account_balances_at` — the union, seven sums per account — rather than
        # on `list_accounts`, which is the cheap indexed read that decides whether the pot holds
        # anything at all and now always runs. Naming the expensive query is also what makes the test
        # discriminate: with `list_accounts` returning [] there is no balance query to make either way,
        # so the pot here HOLDS an account and the guard is the only reason the union is skipped.
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(
            pot_service.snapshot_repository,
            "get_latest_by_investments",
            AsyncMock(return_value={1: self._snapshot(1, date(2026, 6, 10), currency="BRL")}),
        )
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[self._account()]))
        balances = AsyncMock(return_value={})
        monkeypatch.setattr(pot_service.account_service, "compute_account_balances_at", balances)
        await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup(rates={}))
        balances.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_pot_holding_nothing_is_not_reported_as_behind(self, monkeypatch):
        # "No valuation" has two causes and only one is a problem. Demanding a valuation of a pot
        # holding nothing is a demand nobody can satisfy.
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=date(2026, 6, 15), lookup=self._lookup())
        assert (valuation.nav, valuation.valued_as_of, valuation.is_stale) == (None, None, False)

    @pytest.mark.asyncio
    async def test_the_pots_own_cadence_decides_and_ad_hoc_never_does(self, monkeypatch):
        # The same pot, the same snapshot, three cadences: the setting is what makes the answer differ,
        # which is the reason §9 made it a setting rather than a rule.
        monkeypatch.setattr(pot_service.pot_repository, "list_active_investments", AsyncMock(return_value=[_pot_investment(1)]))
        monkeypatch.setattr(
            pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: self._snapshot(1, date(2026, 6, 1))})
        )
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        results = {}
        for cadence in (PotCadence.weekly, PotCadence.monthly, PotCadence.ad_hoc):
            valuation = await pot_service.get_valuation(
                AsyncMock(), _pot(snapshot_cadence=cadence), as_of_date=date(2026, 6, 20), lookup=self._lookup()
            )
            results[cadence] = valuation.is_stale
        assert results == {PotCadence.weekly: True, PotCadence.monthly: False, PotCadence.ad_hoc: False}


class TestCadenceIsPersisted:
    # The cadence is administration, gated like the name and the visibility. A mutation sweep found
    # that nothing asserted the service actually WROTE it — the route test only proves which session
    # the endpoint resolved, and a silently discarded setting is the kind of defect a user only finds
    # when the freshness indicator never changes.

    @pytest.mark.asyncio
    async def test_update_pot_applies_a_new_cadence(self, monkeypatch):
        pot = _pot(snapshot_cadence=PotCadence.monthly)
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=pot))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=_permission(can_view=True)))
        monkeypatch.setattr(pot_service.pot_repository, "save", AsyncMock())
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value=None))
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_admin", AsyncMock())
        session = AsyncMock()
        await pot_service.update_pot(session, 5, USER, snapshot_cadence=PotCadence.weekly)
        assert pot.snapshot_cadence == PotCadence.weekly

    @pytest.mark.asyncio
    async def test_an_omitted_cadence_leaves_the_existing_one_alone(self, monkeypatch):
        # A partial update: renaming a pot must not reset how often it is expected to be re-valued.
        pot = _pot(snapshot_cadence=PotCadence.weekly)
        monkeypatch.setattr(pot_service.pot_repository, "get_by_id", AsyncMock(return_value=pot))
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=_permission(can_view=True)))
        monkeypatch.setattr(pot_service.pot_repository, "save", AsyncMock())
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value=None))
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_admin", AsyncMock())
        await pot_service.update_pot(AsyncMock(), 5, USER, name="Casa")
        assert pot.snapshot_cadence == PotCadence.weekly

    @pytest.mark.asyncio
    async def test_create_pot_records_the_cadence_it_was_given(self, monkeypatch):
        # Asserted on the row the service BUILT, not on what a stub handed back.
        created: list = []

        async def capture(_session, pot):
            created.append(pot)
            pot.id = 5
            return pot

        from app.services import group_service

        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "create", AsyncMock(side_effect=capture))
        monkeypatch.setattr(pot_service.pot_repository, "save_permission", AsyncMock())
        monkeypatch.setattr(pot_service.group_repository, "get_member_by_user", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "list_by_group", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value=None))
        await pot_service.create_pot(AsyncMock(), 10, USER, base_currency="USD", snapshot_cadence=PotCadence.ad_hoc)
        assert created[0].snapshot_cadence == PotCadence.ad_hoc
