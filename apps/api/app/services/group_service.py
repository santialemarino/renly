# Business logic for groups and their member seats (shared money — the people entity).
#
# Two rules govern every function here, and they are the reason the permission checks look the way
# they do:
#   * ownership is a property of the record, never of the login — a group's rows belong to the group,
#     so nothing is filtered by user_id; the membership RLS policies do the scoping;
#   * administration never grants visibility — the admin role gates WRITES to membership, settings and
#     invites, and appears in no read path. An admin sees exactly what any member sees.
#
# Membership is therefore checked in two distinct steps, never one: `_require_member` answers "may you
# see this group at all" (and maps invisible to NotFoundError, so a non-member cannot tell an existing
# group from a missing one), while `require_admin` answers "may you change it".
#
# create_group is the one function that takes the privileged session: the group's first membership row
# is exactly what the RLS policy reads, so the insert cannot satisfy its own predicate. Rather than
# widen the policy with an author-based escape hatch — which would outlive the author's membership —
# the bootstrap runs as the owner, the same posture as the pre-auth invite and auth-token flows.

from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import GroupAdminRequiredError, GroupLastAdminError, NotFoundError
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import group_invite_repository, group_repository
from app.schemas.group import GroupMemberResponse, GroupResponse


# Whether an invite is still usable: minted, never claimed, and not past its window. Expiry is derived
# rather than stored, exactly as the platform invite does it, so a resend just restarts the window.
def _is_live(expires_at: datetime, consumed_at: datetime | None, now: datetime) -> bool:
    return consumed_at is None and expires_at > now


# Builds one member response. `is_self` and `is_linked` are deliberately booleans rather than the seat's
# user_id: a client has no use for another member's account id, and exposing it would leak account
# identity across a group for no gain.
# `is_self` compares SEAT ids, not account ids. Comparing `member.user_id == viewer_user_id` would be
# the obvious form and is a trap: every placeholder seat carries user_id NULL, so the moment a caller
# passed a viewer without an account the comparison would mark all of them as the viewer's own. Seat
# ids are never null on a persisted row, so the ambiguity does not exist to be guarded against.
def _member_response(member: GroupMember, viewer_member_id: int, invited_member_ids: set[int]) -> GroupMemberResponse:
    return GroupMemberResponse(
        id=member.id,
        display_name=member.display_name,
        role=member.role,
        is_active=member.is_active,
        is_linked=member.user_id is not None,
        is_self=member.id == viewer_member_id,
        has_pending_invite=member.id in invited_member_ids,
        joined_at=member.joined_at,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


# Builds a group response from rows already loaded by the caller — so the list path can batch-load
# members and invites once for every group instead of per row.
def _build_response(group: Group, members: list[GroupMember], invited_member_ids: set[int], viewer: GroupMember) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.name,
        kind=group.kind,
        my_role=viewer.role,
        active_member_count=sum(1 for m in members if m.is_active),
        created_at=group.created_at,
        updated_at=group.updated_at,
        members=[_member_response(m, viewer.id, invited_member_ids) for m in members],
    )


# Resolves the caller's own ACTIVE seat in a group, or raises NotFoundError. Used as the visibility
# gate: a non-member (or a former member) gets the same 404 as a group that does not exist, so
# probing ids reveals nothing. RLS already hides the rows; this keeps the service honest on its own.
async def _require_member(session: AsyncSession, group_id: int, user: User) -> tuple[Group, GroupMember]:
    group = await group_repository.get_by_id(session, group_id)
    if group is None:
        raise NotFoundError("Group not found")
    member = await group_repository.get_member_by_user(session, group_id, user.id)
    if member is None or not member.is_active:
        raise NotFoundError("Group not found")
    return (group, member)


# Resolves the caller's own seat and requires it to be an admin one. Separate from _require_member on
# purpose: "can you see it" and "can you change it" are different questions, and collapsing them into
# one check is how an admin-only rule ends up gating a read. Public because group_invite_service gates
# on the same rule, and two copies of a permission check are two things that can disagree.
async def require_admin(session: AsyncSession, group_id: int, user: User) -> tuple[Group, GroupMember]:
    group, member = await _require_member(session, group_id, user)
    if member.role != GroupMemberRole.admin:
        raise GroupAdminRequiredError()
    return (group, member)


# Refuses a change that would leave the group with no active admin — no other role can promote a
# replacement, so the group would be permanently unadministrable.
async def _ensure_admin_remains(session: AsyncSession, group: Group, member: GroupMember) -> None:
    if member.role != GroupMemberRole.admin or not member.is_active:
        return
    if await group_repository.count_active_admins(session, group.id) <= 1:
        raise GroupLastAdminError()


# Lists the groups the user belongs to, each with its full roster. Members and invites are batch-loaded
# for every group at once, so the response costs three queries regardless of how many groups there are.
async def list_groups(session: AsyncSession, user: User) -> list[GroupResponse]:
    groups = await group_repository.list_visible(session)
    group_ids = [g.id for g in groups if g.id is not None]
    members_by_group = await group_repository.list_members_by_groups(session, group_ids)
    invites_by_group = await group_invite_repository.list_by_groups(session, group_ids)
    now = utcnow()

    responses = []
    for group in groups:
        members = members_by_group.get(group.id, [])
        viewer = next((m for m in members if m.user_id == user.id and m.is_active), None)
        # RLS returns only groups the user actively belongs to, so a missing viewer seat would mean the
        # policy and this service disagree. Skip rather than raise: under-reporting is the fail-closed
        # direction, and a 500 on a list page would hide every other group the user does own.
        if viewer is None:
            continue
        invited = {i.member_id for i in invites_by_group.get(group.id, []) if _is_live(i.expires_at, i.consumed_at, now)}
        responses.append(_build_response(group, members, invited, viewer))
    return responses


# Fetches one group with its roster. Raises NotFoundError when it does not exist or the caller is not
# an active member of it.
async def get_group(session: AsyncSession, group_id: int, user: User) -> GroupResponse:
    group, viewer = await _require_member(session, group_id, user)
    members = await group_repository.list_members(session, group.id)
    invites = await group_invite_repository.list_by_group(session, group.id)
    now = utcnow()
    invited = {i.member_id for i in invites if _is_live(i.expires_at, i.consumed_at, now)}
    return _build_response(group, members, invited, viewer)


# Creates a group and seats its creator as the first admin, in one transaction. Runs on the PRIVILEGED
# session — see the module comment: the membership row this needs is the one the RLS policy reads.
async def create_group(
    admin_session: AsyncSession,
    user: User,
    *,
    name: str,
    kind: GroupKind,
    display_name: str | None = None,
) -> GroupResponse:
    group = Group(name=name, kind=kind, created_by=user.id)
    group = await group_repository.create(admin_session, group)
    member = GroupMember(
        group_id=group.id,
        user_id=user.id,
        display_name=display_name or user.name,
        role=GroupMemberRole.admin,
        joined_at=utcnow(),
    )
    member = await group_repository.create_member(admin_session, member)
    await admin_session.commit()
    return _build_response(group, [member], set(), member)


# Renames a group or changes what it is for. Only provided fields are updated. Admin only.
async def update_group(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    name: str | None = None,
    kind: GroupKind | None = None,
) -> GroupResponse:
    group, _ = await require_admin(session, group_id, user)
    if name is not None:
        group.name = name
    if kind is not None:
        group.kind = kind
    await group_repository.save(session, group)
    await session.commit()
    await session.refresh(group)
    return await get_group(session, group.id, user)


# Deletes a group with every seat and invite in it (FK CASCADE). Admin only.
async def delete_group(session: AsyncSession, group_id: int, user: User) -> None:
    group, _ = await require_admin(session, group_id, user)
    await group_repository.delete(session, group)
    await session.commit()


# Adds a name-only seat: someone tracked in the group who has no Renly account linked yet. Inviting
# them is a separate action on the seat, so a person who will never use Renly still gets a real member
# row their share of everything can attach to. Admin only.
async def add_member(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    display_name: str,
    role: GroupMemberRole = GroupMemberRole.member,
) -> GroupResponse:
    group, _ = await require_admin(session, group_id, user)
    await group_repository.create_member(session, GroupMember(group_id=group.id, display_name=display_name, role=role))
    await session.commit()
    return await get_group(session, group.id, user)


# Renames a seat, changes its role, or reactivates a former member. Only provided fields are updated.
# Admin only. Demoting the group's last active admin is refused. Removing a member is DELETE, not
# is_active=false here — see GroupMemberUpdate for why that is not merely a style choice.
async def update_member(
    session: AsyncSession,
    group_id: int,
    member_id: int,
    user: User,
    *,
    display_name: str | None = None,
    role: GroupMemberRole | None = None,
    is_active: Literal[True] | None = None,
) -> GroupResponse:
    group, _ = await require_admin(session, group_id, user)
    member = await group_repository.get_member(session, group.id, member_id)
    if member is None:
        raise NotFoundError("Group member not found")
    # Checked BEFORE mutating, and only when the change actually removes admin rights: demoting the
    # last admin leaves the group unmanageable.
    if role is not None and role != GroupMemberRole.admin:
        await _ensure_admin_remains(session, group, member)
    if display_name is not None:
        member.display_name = display_name
    if role is not None:
        member.role = role
    if is_active:
        member.is_active = True
    await group_repository.save_member(session, member)
    await session.commit()
    # expire_on_commit is False, so the trigger-set updated_at is stale in memory until refreshed.
    await session.refresh(member)
    return await get_group(session, group.id, user)


# Removes a member: deactivates the seat and drops any invite outstanding for it. The seat itself stays,
# so the rows that reference it keep a real counterparty and the group's history stays readable.
# A member may always remove THEMSELVES (leaving the group); removing anyone else needs admin rights.
# Either way the last active admin cannot go, or nobody could manage the group afterwards.
async def remove_member(session: AsyncSession, group_id: int, member_id: int, user: User) -> None:
    group, viewer = await _require_member(session, group_id, user)
    member = await group_repository.get_member(session, group.id, member_id)
    if member is None:
        raise NotFoundError("Group member not found")
    if member.id != viewer.id and viewer.role != GroupMemberRole.admin:
        raise GroupAdminRequiredError()
    await _ensure_admin_remains(session, group, member)
    member.is_active = False
    await group_repository.save_member(session, member)
    # Dropped in the same transaction: leaving a live link on the seat of someone who was just removed
    # would let it re-seat them, and is_active is what the RLS predicate reads.
    await group_invite_repository.delete_by_member(session, member.id)
    await session.commit()
