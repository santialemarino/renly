from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.schemas.group import (
    GroupCreate,
    GroupMemberCreate,
    GroupMemberUpdate,
    GroupResponse,
    GroupUpdate,
)
from app.schemas.group_invite import GroupInviteCreate, GroupInviteCreatedResponse
from app.schemas.shared_audit import SharedAuditEntryResponse
from app.services import group_invite_service, group_service, shared_audit_service

router = APIRouter(prefix="/groups", tags=["groups"])


# Lists the groups the user belongs to, each with its full roster.
@router.get("", response_model=list[GroupResponse])
async def list_groups(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[GroupResponse]:
    return await group_service.list_groups(session, current_user)


# Returns one group with its roster. Returns 404 when it does not exist or the user is not a member —
# the same answer for both, so a non-member cannot tell an existing group from a missing one.
@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    return await group_service.get_group(session, group_id, current_user)


# Creates a group and seats the creator as its first admin. Takes the privileged session because the
# first membership row is the one the group's RLS policy reads, so the insert cannot satisfy it.
@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    current_user: CurrentUser,
    admin_session: AdminSessionDep,
) -> GroupResponse:
    return await group_service.create_group(
        admin_session,
        current_user,
        name=body.name,
        kind=body.kind,
        display_name=body.display_name,
    )


# Updates a group's name or kind. Admin only (403 otherwise). Only provided fields are updated.
@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    body: GroupUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    payload = body.model_dump(exclude_unset=True)
    return await group_service.update_group(session, group_id, current_user, **payload)


# Deletes a group with every seat and invite in it. Admin only (403 otherwise). Returns 204.
@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await group_service.delete_group(session, group_id, current_user)


# Adds a name-only seat to the group. Admin only (403 otherwise). Returns the updated group.
@router.post("/{group_id}/members", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def add_group_member(
    group_id: int,
    body: GroupMemberCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    return await group_service.add_member(session, group_id, current_user, display_name=body.display_name, role=body.role)


# Renames a seat, changes its role, or reactivates a former member. Admin only (403 otherwise).
# Returns 409 when the change would leave the group without an active admin.
@router.put("/{group_id}/members/{member_id}", response_model=GroupResponse)
async def update_group_member(
    group_id: int,
    member_id: int,
    body: GroupMemberUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    payload = body.model_dump(exclude_unset=True)
    return await group_service.update_member(session, group_id, member_id, current_user, **payload)


# Removes a member: deactivates the seat and drops its pending invite. A member may remove themselves
# (leaving the group); removing anyone else is admin only (403). Returns 409 for the last active admin.
@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(
    group_id: int,
    member_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await group_service.remove_member(session, group_id, member_id, current_user)


# Creates or rotates the invite for one seat and emails the link when an address is given. Admin only
# (403 otherwise). The raw link is returned here and nowhere else — nothing stores it, so a lost link
# is replaced by calling this again. Omitting the email produces a link-only invite.
@router.post("/{group_id}/members/{member_id}/invite", response_model=GroupInviteCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_group_invite(
    group_id: int,
    member_id: int,
    body: GroupInviteCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupInviteCreatedResponse:
    return await group_invite_service.create_invite(session, group_id, member_id, current_user, email=body.email)


# Revokes a seat's invite so the link stops working; the seat stays as the placeholder it was. Admin
# only (403 otherwise). Returns 204, including when there was no invite to revoke.
@router.delete("/{group_id}/members/{member_id}/invite", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_group_invite(
    group_id: int,
    member_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await group_invite_service.revoke_invite(session, group_id, member_id, current_user)


# Lists the group's recent activity from the audit trail, newest first. Returns 404 when the caller is
# not a member. Entries about a pot the caller cannot see are absent — the row-level policy decides
# that, so this list never states more than the pot pages themselves would.
@router.get("/{group_id}/activity", response_model=list[SharedAuditEntryResponse])
async def list_group_activity(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    limit: int = Query(
        default=shared_audit_service.DEFAULT_ACTIVITY_PAGE_SIZE,
        ge=1,
        le=shared_audit_service.MAX_ACTIVITY_PAGE_SIZE,
        description="Entries to return.",
    ),
) -> list[SharedAuditEntryResponse]:
    return await shared_audit_service.list_activity(session, group_id, current_user, limit=limit)
