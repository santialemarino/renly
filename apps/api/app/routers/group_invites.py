from fastapi import APIRouter

from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep
from app.schemas.group_invite import GroupInviteAcceptedResponse, GroupInvitePreviewResponse
from app.services import group_invite_service

# The token-facing half of group invites, split from /groups on purpose. Both endpoints address an
# invite by its raw token rather than by a group the caller can already see — the caller is by
# definition not a member yet — so they take the privileged session and cannot be scoped by the
# membership policies. Keeping them on their own prefix also means the token path can never be shadowed
# by /groups/{group_id}, which a path segment under it would be at the mercy of declaration order.
router = APIRouter(prefix="/group-invites", tags=["groups"])


# Returns what a join link is for: the group's name and kind, the seat's label, and who sent it.
# Deliberately unauthenticated — most recipients open the link logged out, and requiring a session to
# read it would strand them. Carries no financial data and no other member's identity. Returns 400 for
# a token that is unknown, already claimed, or expired (one answer for all three, so it cannot be
# probed).
@router.get("/{token}", response_model=GroupInvitePreviewResponse)
async def preview_group_invite(
    token: str,
    admin_session: AdminSessionDep,
) -> GroupInvitePreviewResponse:
    return await group_invite_service.preview_invite(admin_session, token)


# Claims the seat for the authenticated account: links it, stamps joined_at, consumes the invite.
# Returns 400 for a token that is not live or a seat that is no longer claimable, and 409 when the
# caller already holds a seat in that group.
@router.post("/{token}/accept", response_model=GroupInviteAcceptedResponse)
async def accept_group_invite(
    token: str,
    current_user: CurrentUser,
    admin_session: AdminSessionDep,
) -> GroupInviteAcceptedResponse:
    return await group_invite_service.accept_invite(admin_session, token, current_user)
