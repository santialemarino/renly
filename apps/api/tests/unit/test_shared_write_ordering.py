# What has to happen BEFORE what, across the shared-money services.
#
# Two rules, both cross-cutting and both invisible at the call site that gets them wrong.
#
#   * A LOCK comes before the read whose answer is acted on. Every guard in this initiative reads
#     derived state — a ledger, a balance, a settlement's status — and then writes on the strength of
#     it, and none of them can lock the rows the other writer is about to INSERT. So each takes an
#     exclusive lock on the PARENT first. A missing one is not a failing test anywhere: it is two
#     requests a few milliseconds apart, each correct on its own.
#
#   * An audit entry comes before the act that REVOKES the actor's own access. The trail's policy asks
#     whether the writer is still a member and may still see the pot, so leaving a group, or clearing
#     your own view of one, would refuse the very entry that says you did it — and take the whole
#     operation down with it, because the entry rides the same transaction.
#
# Both are asserted on ORDER rather than on presence, because both are already present in the wrong
# place in the version that fails.

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_settlement import GroupSettlement, GroupSettlementStatus
from app.models.pot import Pot, PotMemberPermission
from app.models.user import User
from app.services import group_service, group_settlement_service, pot_ownership_service, pot_service, shared_audit_service

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
POT = Pot(id=5, group_id=10, base_currency="USD", is_default=True)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
OTHER_SEAT = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member)
WRITER = PotMemberPermission(pot_id=5, member_id=100, can_view=True, can_write=True)


# Records the order calls arrive in. Each stub appends its own name, so a test can assert that one step
# precedes another rather than merely that both ran — which is what every rule in this file is about.
class _Trace(list):
    def stub(self, name: str, *, sync: bool = False, result=None):
        def record(*_args, **_kwargs):
            self.append(name)
            return result

        return MagicMock(side_effect=record) if sync else AsyncMock(side_effect=record)

    def index_of(self, name: str) -> int:
        assert name in self, f"{name} never ran: {self}"
        return self.index(name)


class TestTheLockComesFirst:
    @pytest.mark.asyncio
    async def test_an_opening_locks_the_pot_before_reading_the_ledger(self, monkeypatch):
        # The sharpest case in the initiative: "is it already opened" is answered by a SELECT and acted
        # on by an INSERT, so two openings a moment apart both find an empty ledger and the pot ends up
        # divided TWICE — a split summing to 200% that no later act can repair, because record_opening
        # then refuses while any opening row survives.
        trace = _Trace()
        monkeypatch.setattr(pot_ownership_service.pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
        monkeypatch.setattr(pot_ownership_service.pot_repository, "lock", trace.stub("lock"))
        monkeypatch.setattr(pot_ownership_service.pot_ownership_repository, "list_by_pot", trace.stub("read", result=[]))
        monkeypatch.setattr(pot_ownership_service.group_repository, "list_members", AsyncMock(return_value=[SEAT]))
        monkeypatch.setattr(pot_ownership_service.pot_ownership_repository, "create_many", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_ownership_service.pot_service, "list_notifiable_user_ids", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_ownership_service.group_repository, "get_by_id", AsyncMock(return_value=GROUP))
        monkeypatch.setattr(pot_ownership_service.notification_service, "dispatch", AsyncMock())
        monkeypatch.setattr(pot_ownership_service.shared_audit_service, "record", AsyncMock())

        await pot_ownership_service.record_opening(AsyncMock(), 5, USER, date=None, value=Decimal("100"), shares={SEAT.id: Decimal("100")})
        assert trace.index_of("lock") < trace.index_of("read")

    @pytest.mark.asyncio
    async def test_a_movement_locks_the_pot_before_deriving_the_price(self, monkeypatch):
        # Both halves of what follows are read-then-act: the unit price the new units are issued at, and
        # the balance a withdrawal is refused for exceeding. Two withdrawals racing each other both
        # measure a balance neither will still have, and between them redeem more units than exist.
        trace = _Trace()
        monkeypatch.setattr(pot_ownership_service.pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
        monkeypatch.setattr(pot_ownership_service.pot_repository, "lock", trace.stub("lock"))
        monkeypatch.setattr(pot_ownership_service, "_require_price", trace.stub("price", result=(Decimal("1"), {SEAT.id: Decimal("100")})))
        monkeypatch.setattr(pot_ownership_service, "_require_seat", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_ownership_service, "_require_leg", AsyncMock(return_value=None))
        monkeypatch.setattr(pot_ownership_service.pot_ownership_repository, "create", AsyncMock(return_value=MagicMock(id=1)))
        monkeypatch.setattr(pot_ownership_service.pot_service, "list_notifiable_user_ids", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_ownership_service.group_repository, "get_by_id", AsyncMock(return_value=GROUP))
        monkeypatch.setattr(pot_ownership_service.notification_service, "dispatch", AsyncMock())
        monkeypatch.setattr(pot_ownership_service.shared_audit_service, "record", AsyncMock())
        monkeypatch.setattr(pot_ownership_service, "_build_response", MagicMock(return_value="built"))

        from app.models.pot import OwnershipEventType

        await pot_ownership_service.record_movement(
            AsyncMock(), 5, USER, type=OwnershipEventType.contribution, date=None, member_id=SEAT.id, amount=Decimal("10")
        )
        assert trace.index_of("lock") < trace.index_of("price")

    @pytest.mark.asyncio
    async def test_moving_holdings_locks_the_pot_before_reading_the_ledger(self, monkeypatch):
        # Without it a move-out and an opening recorded at the same moment each see a world the other is
        # about to leave, and the move lands on a pot that is divided by the time it commits.
        trace = _Trace()
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "lock", trace.stub("lock"))
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", trace.stub("read", result=[]))
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", AsyncMock())
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", AsyncMock())
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        monkeypatch.setattr(pot_service.shared_audit_service, "record", AsyncMock())

        await pot_service.move_holdings(AsyncMock(), 5, USER, into=True)
        assert trace.index_of("lock") < trace.index_of("read")

    @pytest.mark.asyncio
    async def test_a_write_off_locks_the_group_before_reading_the_balance(self, monkeypatch):
        # A write-off is CAPPED at what is owed, unlike a payment: two recorded at the same moment each
        # measure the whole debt and between them forgive twice it, leaving the debtor owing a negative
        # amount — which is exactly the state the cap exists to prevent.
        trace = _Trace()
        monkeypatch.setattr(group_settlement_service.group_service, "require_member", AsyncMock(return_value=(GROUP, OTHER_SEAT)))
        monkeypatch.setattr(group_settlement_service, "_require_two_seats", AsyncMock(return_value={SEAT.id: SEAT, OTHER_SEAT.id: OTHER_SEAT}))
        monkeypatch.setattr(group_settlement_service.group_repository, "lock", trace.stub("lock"))
        monkeypatch.setattr(group_settlement_service, "_owed_between", trace.stub("balance", result={"ARS": Decimal("100")}))
        monkeypatch.setattr(group_settlement_service.group_settlement_repository, "create", AsyncMock(return_value=MagicMock(id=1)))
        monkeypatch.setattr(group_settlement_service.notification_service, "dispatch", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "_audit", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "_build_response", MagicMock(return_value="built"))

        await group_settlement_service.record_write_off(
            AsyncMock(), 10, USER, from_member_id=SEAT.id, to_member_id=OTHER_SEAT.id, date=None, amount=Decimal("10"), currency="ARS"
        )
        assert trace.index_of("lock") < trace.index_of("balance")

    @pytest.mark.asyncio
    async def test_a_waterfall_locks_the_group_before_reading_the_balance(self, monkeypatch):
        # The allocation is computed from the balances and written as rows, so two waterfalls at once
        # each spill into buckets the other is about to clear.
        trace = _Trace()
        monkeypatch.setattr(group_settlement_service.group_service, "require_member", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(group_settlement_service, "_require_two_seats", AsyncMock(return_value={SEAT.id: SEAT, OTHER_SEAT.id: OTHER_SEAT}))
        monkeypatch.setattr(group_settlement_service, "_ensure_own_leg", MagicMock())
        monkeypatch.setattr(group_settlement_service.group_repository, "lock", trace.stub("lock"))
        monkeypatch.setattr(group_settlement_service, "_owed_between", trace.stub("balance", result={"ARS": Decimal("100")}))
        monkeypatch.setattr(group_settlement_service.group_money_settings_repository, "get_by_group_id", AsyncMock(return_value=None))
        monkeypatch.setattr(group_settlement_service.group_settlement_repository, "create_many", AsyncMock(return_value=[MagicMock(id=1)]))
        monkeypatch.setattr(group_settlement_service, "_settlement_audience", MagicMock(return_value=([], "payee")))
        monkeypatch.setattr(group_settlement_service, "_settlement_payload", MagicMock(return_value={}))
        monkeypatch.setattr(group_settlement_service.notification_service, "dispatch", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "_audit", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "_build_response", MagicMock(return_value="built"))

        await group_settlement_service.record_waterfall(
            AsyncMock(), 10, USER, from_member_id=SEAT.id, to_member_id=OTHER_SEAT.id, date=None, amount=Decimal("50"), currency="ARS"
        )
        assert trace.index_of("lock") < trace.index_of("balance")

    @pytest.mark.asyncio
    async def test_every_settlement_change_locks_the_row_it_is_about_to_change(self, monkeypatch):
        """Confirm, un-confirm, attach a leg and delete all read the status and then act on it.

        Two of them at once both see 'pending' and one acts on a state the other has already left. The
        concrete loss is a CONFIRMED settlement deleted out from under the payee who vouched for it —
        exactly the act the status exists to prevent.
        """
        got = AsyncMock(return_value=None)
        monkeypatch.setattr(group_settlement_service.group_service, "require_member", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(group_settlement_service.group_settlement_repository, "get_by_id", got)
        monkeypatch.setattr(group_settlement_service.group_repository, "list_members", AsyncMock(return_value=[SEAT]))

        from app.domain import NotFoundError

        with pytest.raises(NotFoundError):
            await group_settlement_service.confirm_settlement(AsyncMock(), 10, 1, USER)
        # Asserted on the ARGUMENT rather than on an outcome: a stub returning None raises whether or not
        # the row was locked, so "it raised" would be true of the unlocked version too.
        assert got.await_args.kwargs == {"for_update": True}


class TestTheAuditEntryComesBeforeARevocation:
    @pytest.mark.asyncio
    async def test_leaving_a_group_records_the_departure_before_the_seat_goes(self, monkeypatch):
        """A member may remove THEMSELVES — that is what leaving is.

        The trail's policy asks whether the writer is an active member of the group, so an entry written
        after the seat is deactivated is refused by its own policy, and the whole leave fails with it.
        """
        trace = _Trace()
        target = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.member)
        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, target)))
        monkeypatch.setattr(group_service.group_repository, "get_member", AsyncMock(return_value=target))
        monkeypatch.setattr(group_service, "_ensure_admin_remains", AsyncMock())
        monkeypatch.setattr(group_service.group_repository, "lock", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "ensure_no_outstanding_balance", AsyncMock())
        monkeypatch.setattr(group_service.shared_audit_service, "record", trace.stub("audit"))
        monkeypatch.setattr(group_service.group_repository, "save_member", trace.stub("deactivate"))
        monkeypatch.setattr(group_service.group_invite_repository, "delete_by_member", AsyncMock())

        await group_service.remove_member(AsyncMock(), 10, target.id, USER)
        assert trace.index_of("audit") < trace.index_of("deactivate")

    @pytest.mark.asyncio
    async def test_removal_says_whether_the_member_left_or_was_removed(self, monkeypatch):
        # Two different sentences, and the reader has no way to tell which seat was the actor's.
        recorded = AsyncMock()
        target = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.member)
        other = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.admin)
        monkeypatch.setattr(group_service.group_repository, "get_member", AsyncMock(return_value=target))
        monkeypatch.setattr(group_service, "_ensure_admin_remains", AsyncMock())
        monkeypatch.setattr(group_service.group_repository, "lock", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "ensure_no_outstanding_balance", AsyncMock())
        monkeypatch.setattr(group_service.shared_audit_service, "record", recorded)
        monkeypatch.setattr(group_service.group_repository, "save_member", AsyncMock())
        monkeypatch.setattr(group_service.group_invite_repository, "delete_by_member", AsyncMock())

        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, target)))
        await group_service.remove_member(AsyncMock(), 10, target.id, USER)
        assert recorded.await_args.kwargs["payload"]["variant"] == "self"

        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, other)))
        await group_service.remove_member(AsyncMock(), 10, target.id, USER)
        assert recorded.await_args.kwargs["payload"]["variant"] == "by_admin"

    @pytest.mark.asyncio
    async def test_setting_a_permission_records_before_saving_it(self, monkeypatch):
        # An admin may be revoking their OWN view of an 'owners' pot, and the entry carries that pot's
        # id — so an entry written afterwards fails app_can_view_pot and takes the change with it.
        trace = _Trace()
        monkeypatch.setattr(pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, WRITER)))
        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(pot_service.group_repository, "get_member", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "save_permission", trace.stub("save"))
        monkeypatch.setattr(pot_service.shared_audit_service, "record", trace.stub("audit"))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))

        await pot_service.set_permission(AsyncMock(), 5, SEAT.id, USER, can_view=False, can_write=False)
        assert trace.index_of("audit") < trace.index_of("save")

    @pytest.mark.asyncio
    async def test_clearing_a_permission_records_before_deleting_it(self, monkeypatch):
        # The same revocation from the other direction: dropping your own row on an 'owners' pot leaves
        # you unable to see it, and therefore unable to have written the entry saying you did.
        trace = _Trace()
        monkeypatch.setattr(pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, WRITER)))
        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "get_permission", AsyncMock(return_value=WRITER))
        monkeypatch.setattr(pot_service.group_repository, "get_member", AsyncMock(return_value=SEAT))
        monkeypatch.setattr(pot_service.pot_repository, "delete_permission", trace.stub("delete"))
        monkeypatch.setattr(pot_service.shared_audit_service, "record", trace.stub("audit"))
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))

        await pot_service.clear_permission(AsyncMock(), 5, SEAT.id, USER)
        assert trace.index_of("audit") < trace.index_of("delete")


class TestWhatTheTrailWillNotSay:
    @pytest.mark.asyncio
    async def test_a_pot_deletion_names_no_pot_id(self, monkeypatch):
        """The ONE pot entry written without one, and the reason is that it has to outlive the pot.

        app_can_view_pot cannot answer for a pot that no longer exists, so every OTHER entry about it
        goes dark — the fail-closed direction. This one stays readable because what it discloses is a
        name and an actor, and by here the pot provably held nothing.
        """
        recorded = AsyncMock()
        monkeypatch.setattr(pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, WRITER)))
        monkeypatch.setattr(group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "count_holdings", AsyncMock(return_value=0))
        monkeypatch.setattr(pot_service.pot_repository, "delete", AsyncMock())
        monkeypatch.setattr(pot_service.shared_audit_service, "record", recorded)

        await pot_service.delete_pot(AsyncMock(), 5, USER)
        # `.get`, because the call OMITS the argument rather than passing None — which is the same
        # answer and the honest shape, given `record`'s default is exactly this.
        assert recorded.await_args.kwargs.get("pot_id") is None
        assert recorded.await_args.kwargs["entity_id"] == POT.id

    @pytest.mark.asyncio
    async def test_every_other_pot_entry_names_the_pot_so_it_hides_where_the_pot_does(self, monkeypatch):
        # The counterweight. Without pot_id an entry about an 'owners' pot surfaces on the group's
        # activity feed for members the pot itself is hidden from — an aggregate disclosing what a
        # policy hides, which is the failure this whole visibility rule exists to prevent.
        recorded = AsyncMock()
        monkeypatch.setattr(pot_service, "require_writable", AsyncMock(return_value=(POT, SEAT)))
        monkeypatch.setattr(pot_service.pot_repository, "lock", AsyncMock())
        monkeypatch.setattr(pot_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.investment_repository, "move_to_scope", AsyncMock())
        monkeypatch.setattr(pot_service.account_repository, "move_to_scope", AsyncMock())
        monkeypatch.setattr(pot_service, "get_pot", AsyncMock(return_value="built"))
        monkeypatch.setattr(pot_service.shared_audit_service, "record", recorded)

        await pot_service.move_holdings(AsyncMock(), 5, USER, into=True)
        assert recorded.await_args.kwargs["pot_id"] == POT.id

    @pytest.mark.asyncio
    async def test_an_invite_entry_carries_neither_the_address_nor_the_link(self, monkeypatch):
        """Both are things an entry every member reads must not hold.

        The address belongs to the invitee, and the raw token is the one value token_hash exists to keep
        out of readable data — a stored link would hand any member the seat somebody else was invited to.
        """
        from app.services import group_invite_service

        recorded = AsyncMock()
        seat = GroupMember(id=102, group_id=10, user_id=None, display_name="Nico", role=GroupMemberRole.member)
        monkeypatch.setattr(group_invite_service.group_service, "require_admin", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(group_invite_service.group_repository, "get_member", AsyncMock(return_value=seat))
        monkeypatch.setattr(group_invite_service.group_invite_repository, "get_by_member", AsyncMock(return_value=None))
        monkeypatch.setattr(group_invite_service.group_invite_repository, "create", AsyncMock())
        monkeypatch.setattr(group_invite_service.group_service, "list_notifiable_user_ids", AsyncMock(return_value=[]))
        monkeypatch.setattr(group_invite_service.notification_service, "dispatch", AsyncMock())
        monkeypatch.setattr(group_invite_service.settings_service, "get_user_language", AsyncMock(return_value="en"))
        monkeypatch.setattr(group_invite_service, "_safe_send", AsyncMock())
        monkeypatch.setattr(group_invite_service.shared_audit_service, "record", recorded)

        await group_invite_service.create_invite(AsyncMock(), 10, seat.id, USER, email="nico@example.com")
        # The whole payload, not a subset: asserting the address is absent would pass on an entry that
        # carried it under another name, and this is the one payload where a leak is a real disclosure.
        assert recorded.await_args.kwargs["payload"] == {"member": "Nico"}

    @pytest.mark.asyncio
    async def test_a_cash_leg_entry_names_no_account(self, monkeypatch):
        # Which of the caller's OWN accounts the money passed through is a fact only they can see — the
        # row-level policies hide everyone else's — so an entry every member reads may say a leg was
        # attached and nothing about which account it was.
        recorded = AsyncMock()
        settlement = GroupSettlement(
            id=1,
            group_id=10,
            from_member_id=SEAT.id,
            to_member_id=OTHER_SEAT.id,
            date=None,
            amount=Decimal("50"),
            currency="ARS",
            status=GroupSettlementStatus.pending,
        )
        monkeypatch.setattr(
            group_settlement_service,
            "_require_settlement",
            AsyncMock(return_value=(settlement, GROUP, {SEAT.id: SEAT, OTHER_SEAT.id: OTHER_SEAT}, SEAT)),
        )
        monkeypatch.setattr(group_settlement_service, "_resolve_leg", AsyncMock(return_value=None))
        monkeypatch.setattr(group_settlement_service.group_settlement_repository, "save", AsyncMock())
        monkeypatch.setattr(group_settlement_service, "_build_response", MagicMock(return_value="built"))
        monkeypatch.setattr(shared_audit_service, "record", recorded)

        await group_settlement_service.set_leg(AsyncMock(), 10, 1, USER, account_id=7)
        payload = recorded.await_args.kwargs["payload"]
        assert "account" not in payload and 7 not in payload.values()
        assert payload["variant"] == "attached"
