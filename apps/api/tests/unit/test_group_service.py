# Unit coverage for the group service: the visibility gate (a non-member gets the same answer as a
# missing group), the admin gate on every write, the last-admin guard, the response shape's derived
# booleans, and the batch-load that keeps list_groups off an N+1.
#
# Every guard here is a product rule stated in the service, so it is tested in the service. The
# database-level half — that RLS hides another group's rows at all — is proven in
# tests/integration/test_rls_isolation.py against a real Postgres, because a mocked session cannot
# notice a policy that has stopped working.

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.domain import GroupAdminRequiredError, GroupBalanceOutstandingError, GroupLastAdminError, NotFoundError
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_invite import GroupInvite
from app.models.user import User
from app.models.utils import utcnow
from app.services import group_money_service, group_service, group_settlement_service

ADMIN = User(id=1, name="Santi", email="admin@test", password_hash="x", session_epoch=0)
MEMBER = User(id=2, name="Ana", email="ana@test", password_hash="x", session_epoch=0)
OUTSIDER = User(id=3, name="Bob", email="bob@test", password_hash="x", session_epoch=0)

_GROUP_ID = 10


# Builds a group with no money-specific fields — `groups` is deliberately entity-agnostic.
def _group(group_id: int = _GROUP_ID, name: str = "Casa") -> Group:
    return Group(id=group_id, name=name, kind=GroupKind.household, created_by=ADMIN.id)


# Builds a seat. user_id=None is a name-only placeholder (someone with no Renly account).
def _member(
    member_id: int,
    *,
    user_id: int | None = None,
    display_name: str = "Seat",
    role: GroupMemberRole = GroupMemberRole.member,
    is_active: bool = True,
) -> GroupMember:
    return GroupMember(
        id=member_id,
        group_id=_GROUP_ID,
        user_id=user_id,
        display_name=display_name,
        role=role,
        is_active=is_active,
    )


# Builds a live invite for a seat (unconsumed, inside its window).
def _invite(member_id: int, *, consumed: bool = False, expired: bool = False) -> GroupInvite:
    now = utcnow()
    return GroupInvite(
        id=member_id + 100,
        group_id=_GROUP_ID,
        member_id=member_id,
        token_hash=f"hash-{member_id}",
        expires_at=now - timedelta(days=1) if expired else now + timedelta(days=7),
        consumed_at=now if consumed else None,
    )


# Points the group repository at the given return values; unset methods stay AsyncMock() no-ops.
def _patch_repo(monkeypatch, **methods):
    for name in (
        "count_active_admins",
        "create",
        "create_member",
        "delete",
        "get_by_id",
        "get_member",
        "get_member_by_user",
        "list_members",
        "list_members_by_groups",
        "list_visible",
        "save",
        "save_member",
    ):
        monkeypatch.setattr(group_service.group_repository, name, methods.get(name, AsyncMock()))


# Points the group-invite repository at the given return values.
def _patch_invite_repo(monkeypatch, **methods):
    for name in ("delete_by_member", "list_by_group", "list_by_groups"):
        monkeypatch.setattr(group_service.group_invite_repository, name, methods.get(name, AsyncMock(return_value=[])))


# Stubs the outstanding-balance guard removal now runs. Patched on the settlement service's own module
# rather than through group_service, because group_service imports it INSIDE the function to break the
# cycle between the two — an attribute patched on group_service would never be looked at.
# Returns the mock so a test can assert the guard was actually consulted rather than assumed.
def _patch_balance_guard(monkeypatch, **methods) -> AsyncMock:
    guard = methods.get("ensure_no_outstanding_balance", AsyncMock())
    monkeypatch.setattr(group_settlement_service, "ensure_no_outstanding_balance", guard)
    return guard


# Stubs the money-settings row every group creation seeds.
def _patch_money_settings(monkeypatch) -> AsyncMock:
    seed = AsyncMock()
    monkeypatch.setattr(group_money_service, "seed_settings", seed)
    return seed


# Stands in for the repository's create_member, which flushes so the DB assigns the seat's id — the
# response builder needs it, so a mock that skips it would not exercise the real shape.
async def _flushed(_session, member: GroupMember) -> GroupMember:
    member.id = 1
    return member


# The same for create(): the group's id comes from the flush, and the response cannot be built without
# it. Returning the very object the service constructed is the point — that is what makes the create
# assertions test the service rather than the fixture.
async def _flushed_group(_session, group: Group) -> Group:
    group.id = _GROUP_ID
    return group


class TestVisibilityGate:
    @pytest.mark.asyncio
    async def test_a_non_member_gets_not_found_rather_than_forbidden(self, monkeypatch):
        # The same answer a missing group gives, so probing ids reveals nothing about which exist.
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member_by_user=AsyncMock(return_value=None))
        _patch_invite_repo(monkeypatch)
        with pytest.raises(NotFoundError):
            await group_service.get_group(AsyncMock(), _GROUP_ID, OUTSIDER)

    @pytest.mark.asyncio
    async def test_a_former_member_can_no_longer_see_the_group(self, monkeypatch):
        removed = _member(2, user_id=MEMBER.id, is_active=False)
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member_by_user=AsyncMock(return_value=removed))
        _patch_invite_repo(monkeypatch)
        with pytest.raises(NotFoundError):
            await group_service.get_group(AsyncMock(), _GROUP_ID, MEMBER)

    @pytest.mark.asyncio
    async def test_a_plain_member_sees_the_whole_roster(self, monkeypatch):
        # Administration never grants visibility, so a member's read is identical to an admin's.
        seat = _member(2, user_id=MEMBER.id, display_name="Ana")
        roster = [_member(1, user_id=ADMIN.id, display_name="Santi", role=GroupMemberRole.admin), seat, _member(3, display_name="Nico")]
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=roster),
        )
        _patch_invite_repo(monkeypatch)
        response = await group_service.get_group(AsyncMock(), _GROUP_ID, MEMBER)
        assert [m.display_name for m in response.members] == ["Santi", "Ana", "Nico"]
        assert response.my_role == GroupMemberRole.member
        assert response.active_member_count == 3


class TestResponseShape:
    @pytest.mark.asyncio
    async def test_exactly_one_seat_is_marked_as_the_viewers_own(self, monkeypatch):
        # Two placeholder seats both carry user_id NULL, so an is_self built on account ids would mark
        # both of them as the viewer's. It is built on seat ids, which are never null.
        seat = _member(2, user_id=MEMBER.id, display_name="Ana")
        roster = [_member(1, user_id=ADMIN.id, display_name="Santi"), seat, _member(3, display_name="Nico"), _member(4, display_name="Vale")]
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=roster),
        )
        _patch_invite_repo(monkeypatch)
        response = await group_service.get_group(AsyncMock(), _GROUP_ID, MEMBER)
        assert [(m.display_name, m.is_self, m.is_linked) for m in response.members] == [
            ("Santi", False, True),
            ("Ana", True, True),
            ("Nico", False, False),
            ("Vale", False, False),
        ]
        assert sum(1 for m in response.members if m.is_self) == 1

    @pytest.mark.asyncio
    async def test_a_viewer_with_no_account_on_their_seat_marks_only_that_seat(self, monkeypatch):
        # The state that would break an account-id comparison, exercised directly: a viewer seat with
        # user_id NULL alongside two other placeholders. Only the viewer's own seat may come back self.
        seat = _member(3, display_name="Placeholder viewer")
        roster = [_member(2, display_name="Nico"), seat, _member(4, display_name="Vale")]
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=roster),
        )
        _patch_invite_repo(monkeypatch)
        response = await group_service.get_group(AsyncMock(), _GROUP_ID, MEMBER)
        assert [(m.display_name, m.is_self) for m in response.members] == [
            ("Nico", False),
            ("Placeholder viewer", True),
            ("Vale", False),
        ]

    @pytest.mark.asyncio
    async def test_no_member_response_exposes_an_account_id(self, monkeypatch):
        # A client has no use for another member's user id, and exposing it would leak account
        # identity across a group.
        seat = _member(2, user_id=MEMBER.id)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=[seat]),
        )
        _patch_invite_repo(monkeypatch)
        response = await group_service.get_group(AsyncMock(), _GROUP_ID, MEMBER)
        assert "user_id" not in response.members[0].model_dump()

    @pytest.mark.asyncio
    async def test_only_a_live_invite_marks_a_seat_as_invited(self, monkeypatch):
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        roster = [seat, _member(2, display_name="live"), _member(3, display_name="consumed"), _member(4, display_name="expired")]
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=roster),
        )
        _patch_invite_repo(
            monkeypatch,
            list_by_group=AsyncMock(return_value=[_invite(2), _invite(3, consumed=True), _invite(4, expired=True)]),
        )
        response = await group_service.get_group(AsyncMock(), _GROUP_ID, ADMIN)
        assert {m.display_name: m.has_pending_invite for m in response.members} == {
            "Seat": False,
            "live": True,
            "consumed": False,
            "expired": False,
        }

    @pytest.mark.asyncio
    async def test_active_member_count_excludes_former_members(self, monkeypatch):
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        roster = [seat, _member(2), _member(3, is_active=False)]
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=roster),
        )
        _patch_invite_repo(monkeypatch)
        response = await group_service.get_group(AsyncMock(), _GROUP_ID, ADMIN)
        assert response.active_member_count == 2
        assert len(response.members) == 3


class TestListGroups:
    @pytest.mark.asyncio
    async def test_rosters_and_invites_are_batch_loaded_not_queried_per_group(self, monkeypatch):
        groups = [_group(10, "Casa"), _group(11, "Viaje")]
        seats = {
            10: [_member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)],
            11: [GroupMember(id=2, group_id=11, user_id=ADMIN.id, display_name="Santi", role=GroupMemberRole.member)],
        }
        batch_members = AsyncMock(return_value=seats)
        per_group_members = AsyncMock(return_value=[])
        batch_invites = AsyncMock(return_value={})
        per_group_invites = AsyncMock(return_value=[])
        _patch_repo(
            monkeypatch,
            list_visible=AsyncMock(return_value=groups),
            list_members_by_groups=batch_members,
            list_members=per_group_members,
        )
        _patch_invite_repo(monkeypatch, list_by_groups=batch_invites, list_by_group=per_group_invites)

        responses = await group_service.list_groups(AsyncMock(), ADMIN)
        assert [r.name for r in responses] == ["Casa", "Viaje"]
        assert [r.my_role for r in responses] == [GroupMemberRole.admin, GroupMemberRole.member]
        # One batch call each, carrying every id — and neither single-group variant used in the loop.
        assert batch_members.await_count == 1
        assert batch_members.await_args.args[1] == [10, 11]
        assert batch_invites.await_count == 1
        assert batch_invites.await_args.args[1] == [10, 11]
        per_group_members.assert_not_awaited()
        per_group_invites.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_group_with_no_seat_for_the_viewer_is_omitted_rather_than_raising(self, monkeypatch):
        # Under-reporting is the fail-closed direction: a policy/service disagreement must not blank
        # out every other group the user really does belong to.
        mine = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        _patch_repo(
            monkeypatch,
            list_visible=AsyncMock(return_value=[_group(10, "Casa"), _group(11, "Ajena")]),
            list_members_by_groups=AsyncMock(return_value={10: [mine], 11: [GroupMember(id=9, group_id=11, display_name="x")]}),
        )
        _patch_invite_repo(monkeypatch, list_by_groups=AsyncMock(return_value={}))
        assert [r.name for r in await group_service.list_groups(AsyncMock(), ADMIN)] == ["Casa"]


class TestCreateGroup:
    @pytest.mark.asyncio
    async def test_the_creator_is_seated_as_the_first_admin(self, monkeypatch):
        # Asserted on the ROWS THE SERVICE BUILT, not on a mock's return value. Handing back a
        # hardcoded admin member made the earlier version of this test pass even with the service
        # seating the creator as a plain member — it was checking the fixture, not the code.
        create = AsyncMock(side_effect=_flushed_group)
        create_member = AsyncMock(side_effect=_flushed)
        _patch_repo(monkeypatch, create=create, create_member=create_member)
        _patch_invite_repo(monkeypatch)
        session = AsyncMock()

        response = await group_service.create_group(session, ADMIN, name="Casa", kind=GroupKind.household)

        seat = create_member.await_args.args[1]
        assert seat.user_id == ADMIN.id
        assert seat.role == GroupMemberRole.admin
        assert seat.is_active is True
        assert seat.joined_at is not None
        assert response.my_role == GroupMemberRole.admin
        assert response.active_member_count == 1
        assert response.members[0].is_self is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_every_group_gets_its_money_settings_row(self, monkeypatch):
        # Written in the same transaction and on the same PRIVILEGED session, because the table shares
        # the membership policy whose row does not exist yet either. Every reader then joins one row
        # rather than carrying an "or the default" branch — and a group without it answers 404 on its
        # settings, which is a broken invariant rather than a defaulting case.
        #
        # Asserted on the GROUP ID the service passed: dropping the call entirely left every other
        # create-group test green, which a mutation sweep is what surfaced.
        _patch_repo(monkeypatch, create=AsyncMock(side_effect=_flushed_group), create_member=AsyncMock(side_effect=_flushed))
        _patch_invite_repo(monkeypatch)
        seed = _patch_money_settings(monkeypatch)
        session = AsyncMock()

        await group_service.create_group(session, ADMIN, name="Casa", kind=GroupKind.household)

        assert seed.await_count == 1
        assert seed.await_args.args[0] is session
        assert seed.await_args.args[1] == _GROUP_ID

    @pytest.mark.asyncio
    async def test_the_group_records_its_name_kind_and_author(self, monkeypatch):
        # created_by is authorship and the only trace of who made the group; nothing else records it.
        create = AsyncMock(side_effect=_flushed_group)
        _patch_repo(monkeypatch, create=create, create_member=AsyncMock(side_effect=_flushed))
        _patch_invite_repo(monkeypatch)
        await group_service.create_group(AsyncMock(), ADMIN, name="Casa", kind=GroupKind.couple)
        built = create.await_args.args[1]
        assert (built.name, built.kind, built.created_by) == ("Casa", GroupKind.couple, ADMIN.id)

    @pytest.mark.asyncio
    async def test_the_seat_falls_back_to_the_account_name_when_none_is_given(self, monkeypatch):
        create_member = AsyncMock(side_effect=_flushed)
        _patch_repo(monkeypatch, create=AsyncMock(return_value=_group()), create_member=create_member)
        _patch_invite_repo(monkeypatch)
        await group_service.create_group(AsyncMock(), ADMIN, name="Casa", kind=GroupKind.household)
        assert create_member.await_args.args[1].display_name == "Santi"

    @pytest.mark.asyncio
    async def test_a_given_display_name_wins_over_the_account_name(self, monkeypatch):
        create_member = AsyncMock(side_effect=_flushed)
        _patch_repo(monkeypatch, create=AsyncMock(return_value=_group()), create_member=create_member)
        _patch_invite_repo(monkeypatch)
        await group_service.create_group(AsyncMock(), ADMIN, name="Casa", kind=GroupKind.household, display_name="Papá")
        assert create_member.await_args.args[1].display_name == "Papá"


class TestAdminGate:
    # Each write path is gated independently: one shared predicate is what keeps them from drifting,
    # and one test per path is what proves none of them forgot to call it.
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda s: group_service.update_group(s, _GROUP_ID, MEMBER, name="Nueva"), id="update_group"),
            pytest.param(lambda s: group_service.delete_group(s, _GROUP_ID, MEMBER), id="delete_group"),
            pytest.param(lambda s: group_service.add_member(s, _GROUP_ID, MEMBER, display_name="Nico"), id="add_member"),
            pytest.param(lambda s: group_service.update_member(s, _GROUP_ID, 3, MEMBER, display_name="Nico"), id="update_member"),
        ],
    )
    async def test_a_plain_member_cannot_write(self, monkeypatch, call):
        seat = _member(2, user_id=MEMBER.id, role=GroupMemberRole.member)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            get_member=AsyncMock(return_value=_member(3)),
        )
        _patch_invite_repo(monkeypatch)
        with pytest.raises(GroupAdminRequiredError):
            await call(AsyncMock())

    @pytest.mark.asyncio
    async def test_an_admin_can_rename_the_group(self, monkeypatch):
        group = _group()
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        save = AsyncMock()
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=group),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=[seat]),
            save=save,
        )
        _patch_invite_repo(monkeypatch)
        response = await group_service.update_group(AsyncMock(), _GROUP_ID, ADMIN, name="Casa Nueva", kind=GroupKind.couple)
        assert group.name == "Casa Nueva"
        assert group.kind == GroupKind.couple
        assert response.name == "Casa Nueva"
        save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_new_member_is_created_as_a_placeholder_with_no_account(self, monkeypatch):
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        create_member = AsyncMock(side_effect=_flushed)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=[seat]),
            create_member=create_member,
        )
        _patch_invite_repo(monkeypatch)
        await group_service.add_member(AsyncMock(), _GROUP_ID, ADMIN, display_name="Nico")
        added = create_member.await_args.args[1]
        assert added.user_id is None
        assert added.display_name == "Nico"
        assert added.joined_at is None


class TestLastAdminGuard:
    @pytest.mark.asyncio
    async def test_the_only_admin_cannot_be_demoted(self, monkeypatch):
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            get_member=AsyncMock(return_value=seat),
            count_active_admins=AsyncMock(return_value=1),
        )
        _patch_invite_repo(monkeypatch)
        with pytest.raises(GroupLastAdminError):
            await group_service.update_member(AsyncMock(), _GROUP_ID, 1, ADMIN, role=GroupMemberRole.member)

    @pytest.mark.asyncio
    async def test_the_only_admin_cannot_leave(self, monkeypatch):
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            get_member=AsyncMock(return_value=seat),
            count_active_admins=AsyncMock(return_value=1),
        )
        _patch_invite_repo(monkeypatch)
        with pytest.raises(GroupLastAdminError):
            await group_service.remove_member(AsyncMock(), _GROUP_ID, 1, ADMIN)

    @pytest.mark.asyncio
    async def test_one_of_two_admins_may_be_demoted(self, monkeypatch):
        seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            get_member=AsyncMock(return_value=seat),
            list_members=AsyncMock(return_value=[seat]),
            count_active_admins=AsyncMock(return_value=2),
        )
        _patch_invite_repo(monkeypatch)
        await group_service.update_member(AsyncMock(), _GROUP_ID, 1, ADMIN, role=GroupMemberRole.member)
        assert seat.role == GroupMemberRole.member

    @pytest.mark.asyncio
    async def test_removing_a_plain_member_never_consults_the_admin_count(self, monkeypatch):
        # The guard is scoped to admin seats: charging it on every removal would be a needless query
        # and would read as though a group needed a minimum size.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        count = AsyncMock(return_value=1)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=AsyncMock(return_value=_member(3, display_name="Nico")),
            count_active_admins=count,
        )
        _patch_invite_repo(monkeypatch)
        _patch_balance_guard(monkeypatch)
        await group_service.remove_member(AsyncMock(), _GROUP_ID, 3, ADMIN)
        count.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_already_inactive_admin_seat_does_not_trip_the_guard(self, monkeypatch):
        # Deactivating a seat that is already inactive removes no live admin, so it must not be
        # refused as "the last admin" — otherwise a former admin could never be edited again.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        former_admin = _member(2, display_name="Ex", role=GroupMemberRole.admin, is_active=False)
        count = AsyncMock(return_value=1)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=AsyncMock(return_value=former_admin),
            list_members=AsyncMock(return_value=[admin_seat, former_admin]),
            count_active_admins=count,
        )
        _patch_invite_repo(monkeypatch)
        await group_service.update_member(AsyncMock(), _GROUP_ID, 2, ADMIN, role=GroupMemberRole.member)
        count.assert_not_awaited()


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removal_deactivates_the_seat_rather_than_deleting_it(self, monkeypatch):
        # The seat must survive: the rows that will reference it need a real counterparty, and its
        # history stays readable to the group.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        target = _member(3, display_name="Nico")
        save_member = AsyncMock()
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=AsyncMock(return_value=target),
            save_member=save_member,
        )
        _patch_invite_repo(monkeypatch)
        _patch_balance_guard(monkeypatch)
        await group_service.remove_member(AsyncMock(), _GROUP_ID, 3, ADMIN)
        assert target.is_active is False
        save_member.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_removal_revokes_the_seats_pending_invite(self, monkeypatch):
        # Leaving the link alive would let it re-seat someone who was just removed.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        target = _member(3, display_name="Nico")
        delete_invite = AsyncMock()
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=AsyncMock(return_value=target),
        )
        _patch_invite_repo(monkeypatch, delete_by_member=delete_invite)
        _patch_balance_guard(monkeypatch)
        await group_service.remove_member(AsyncMock(), _GROUP_ID, 3, ADMIN)
        assert delete_invite.await_count == 1
        assert delete_invite.await_args.args[1] == 3

    @pytest.mark.asyncio
    async def test_removal_is_refused_while_the_seat_still_owes_or_is_owed(self, monkeypatch):
        # D24: a balance is money between two real people, and deactivating the seat is what takes the
        # group's rows away from them. Asserted on the SEAT the guard was handed, not merely that it
        # ran — passing the wrong one would guard somebody else's balance and pass just as quietly.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        target = _member(3, display_name="Nico")
        save_member = AsyncMock()
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=AsyncMock(return_value=target),
            save_member=save_member,
        )
        _patch_invite_repo(monkeypatch)
        guard = _patch_balance_guard(monkeypatch, ensure_no_outstanding_balance=AsyncMock(side_effect=GroupBalanceOutstandingError(["Casa"])))

        with pytest.raises(GroupBalanceOutstandingError):
            await group_service.remove_member(AsyncMock(), _GROUP_ID, 3, ADMIN)

        assert guard.await_args.args[1] == [target]
        # And nothing was written: the refusal has to land before the seat is deactivated, or the
        # rollback is the only thing standing between a raised error and a removed member.
        assert target.is_active is True
        save_member.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reactivating_through_the_update_path_does_not_touch_any_invite(self, monkeypatch):
        # is_active on the PUT is reactivate-ONLY (Literal[True]); removal is the DELETE verb, which is
        # what also drops the pending invite. A returning member's seat has no invite to drop, and
        # calling the removal path here would be a needless write on every reactivation.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        target = _member(3, display_name="Nico", is_active=False)
        delete_invite = AsyncMock()
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=AsyncMock(return_value=target),
            list_members=AsyncMock(return_value=[admin_seat, target]),
        )
        _patch_invite_repo(monkeypatch, delete_by_member=delete_invite)
        await group_service.update_member(AsyncMock(), _GROUP_ID, 3, ADMIN, is_active=True)
        assert target.is_active is True
        delete_invite.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_plain_member_may_remove_their_own_seat(self, monkeypatch):
        # Leaving a group must not require an admin — otherwise a member could be held in one.
        seat = _member(2, user_id=MEMBER.id, role=GroupMemberRole.member)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            get_member=AsyncMock(return_value=seat),
        )
        _patch_invite_repo(monkeypatch)
        _patch_balance_guard(monkeypatch)
        await group_service.remove_member(AsyncMock(), _GROUP_ID, 2, MEMBER)
        assert seat.is_active is False

    @pytest.mark.asyncio
    async def test_a_plain_member_cannot_remove_someone_else(self, monkeypatch):
        seat = _member(2, user_id=MEMBER.id, role=GroupMemberRole.member)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=seat),
            get_member=AsyncMock(return_value=_member(3, display_name="Nico")),
        )
        _patch_invite_repo(monkeypatch)
        with pytest.raises(GroupAdminRequiredError):
            await group_service.remove_member(AsyncMock(), _GROUP_ID, 3, MEMBER)

    @pytest.mark.asyncio
    async def test_a_member_id_from_another_group_is_not_found(self, monkeypatch):
        # get_member is scoped to the group, so an id belonging elsewhere resolves to nothing —
        # without that scoping an admin of one group could edit another group's seat by id.
        admin_seat = _member(1, user_id=ADMIN.id, role=GroupMemberRole.admin)
        get_member = AsyncMock(return_value=None)
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member_by_user=AsyncMock(return_value=admin_seat),
            get_member=get_member,
        )
        _patch_invite_repo(monkeypatch)
        with pytest.raises(NotFoundError):
            await group_service.remove_member(AsyncMock(), _GROUP_ID, 999, ADMIN)
        assert get_member.await_args.args[1] == _GROUP_ID
