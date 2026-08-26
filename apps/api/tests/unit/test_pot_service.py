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
    NotFoundError,
    PotHasHoldingsError,
    PotWriteRequiredError,
)
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.investment import Investment, InvestmentCategory
from app.models.pot import Pot, PotMemberPermission, PotVisibility
from app.models.user import User
from app.services import pot_service

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
OTHER = User(id=2, name="Ana", email="a@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
PLAIN_SEAT = GroupMember(id=101, group_id=10, user_id=OTHER.id, display_name="Ana", role=GroupMemberRole.member)


def _pot(**kwargs) -> Pot:
    defaults = dict(id=5, group_id=10, name=None, base_currency="USD", visibility=PotVisibility.members, is_default=True)
    return Pot(**{**defaults, **kwargs})


def _permission(**kwargs) -> PotMemberPermission:
    defaults = dict(pot_id=5, member_id=100, can_view=True, can_write=False)
    return PotMemberPermission(**{**defaults, **kwargs})


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
        assert pot_service._may_write(None) is False
        assert pot_service._may_write(_permission(can_write=False)) is False
        assert pot_service._may_write(_permission(can_view=True, can_write=True)) is True


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
        for repo in ("income_repository", "expense_repository", "card_settlement_repository"):
            monkeypatch.setattr(getattr(pot_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(pot_service.transfer_repository, "linked_account_ids", AsyncMock(return_value={7}))
        monkeypatch.setattr(pot_service.transfer_repository, "exists_for_accounts", AsyncMock(return_value=False))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "exists_for_accounts", AsyncMock(return_value=False))
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
        for repo in ("income_repository", "expense_repository", "card_settlement_repository", "transfer_repository"):
            monkeypatch.setattr(getattr(pot_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(pot_service.transfer_repository, "exists_for_accounts", AsyncMock(return_value=False))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "exists_for_accounts", AsyncMock(return_value=True))
        move = AsyncMock(return_value=1)
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", move)
        with pytest.raises(AccountHasLinkedEntriesError):
            await pot_service.move_holdings(AsyncMock(), 5, USER, account_ids=[7])
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_clean_account_moves_in(self, monkeypatch):
        # The positive control for both guards: without it, "raises" above would pass even if the
        # method refused every account unconditionally.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.account_repository, "get_by_ids_any_scope", AsyncMock(return_value=[self._account(7)]))
        for repo in ("income_repository", "expense_repository", "card_settlement_repository", "transfer_repository"):
            monkeypatch.setattr(getattr(pot_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(pot_service.transfer_repository, "exists_for_accounts", AsyncMock(return_value=False))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "exists_for_accounts", AsyncMock(return_value=False))
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
    async def test_moving_IN_is_unaffected_by_the_ledger(self, monkeypatch):
        # The guard is one-directional on purpose: adding to a divided pot takes nothing from anyone,
        # it only dilutes percentages in the contributor's favour — which is what a contribution is.
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(_pot(), SEAT)))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[object()]))
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
        for repo in ("income_repository", "expense_repository", "card_settlement_repository", "transfer_repository"):
            monkeypatch.setattr(getattr(pot_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(pot_service.transfer_repository, "exists_for_accounts", AsyncMock(return_value=True))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "exists_for_accounts", AsyncMock(return_value=False))
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
        for repo in ("income_repository", "expense_repository", "card_settlement_repository", "transfer_repository"):
            monkeypatch.setattr(getattr(pot_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(pot_service.transfer_repository, "exists_for_accounts", AsyncMock(return_value=False))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "exists_for_accounts", AsyncMock(return_value=False))
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


class TestNav:
    @pytest.mark.asyncio
    async def test_an_unconvertible_holding_makes_the_nav_unknown_rather_than_understated(self, monkeypatch):
        # Fail-loud, and it matters more here than anywhere else: an understated NAV would silently
        # misprice every unit issued against it.
        from app.models.snapshot import InvestmentSnapshot

        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 1, 1), value=Decimal("100"), currency="BRL")
        monkeypatch.setattr(pot_service.pot_repository, "list_investment_ids", AsyncMock(return_value=[1]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: snapshot}))
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
        monkeypatch.setattr(pot_service.pot_repository, "list_investment_ids", AsyncMock(return_value=[1]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", latest)
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup)
        assert latest.await_args.kwargs == {"as_of_date": date(2026, 6, 1)}

    @pytest.mark.asyncio
    async def test_a_pot_whose_holdings_have_no_snapshot_by_that_date_is_worth_zero(self, monkeypatch):
        monkeypatch.setattr(pot_service.pot_repository, "list_investment_ids", AsyncMock(return_value=[1]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={}))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        assert await pot_service.get_nav(AsyncMock(), _pot(), as_of_date=date(2026, 6, 1), lookup=lookup) == Decimal(0)
