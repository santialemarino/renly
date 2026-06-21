from fastapi import APIRouter, Request, Response

from app.deps.auth import AdminUser
from app.deps.db import AdminSessionDep
from app.models.invite import Invite
from app.rate_limit import INVITE_LIMIT, limiter
from app.schemas.invite import CreateInviteRequest, InviteResponse
from app.services import invite_service

router = APIRouter(prefix="/admin", tags=["admin"])

# Admin-only invite management for the invite-only access gate. Every endpoint requires is_admin
# (AdminUser → 403 otherwise) and runs the invite work on the privileged session, whose reads span
# all invites regardless of who created them. Hiding the page from non-admins is the web's job (a
# 404); the API authorization here is the real gate.

# NOTE: every @limiter.limit endpoint must declare a `response: Response` parameter so slowapi can
# inject the X-RateLimit-* headers on the success path (headers_enabled).


# Maps an invite row to its response, computing the effective status (pending invites past their
# expiry read as "expired").
def _to_response(invite: Invite) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        email=invite.email,
        status=invite_service.effective_status(invite),
        invited_by=invite.invited_by,
        expires_at=invite.expires_at,
        consumed_at=invite.consumed_at,
        created_at=invite.created_at,
    )


# Lists every invite with its status (admin invite management view).
@router.get("/invites", response_model=list[InviteResponse])
async def list_invites(admin: AdminUser, session: AdminSessionDep) -> list[InviteResponse]:
    invites = await invite_service.list_invites(session)
    return [_to_response(invite) for invite in invites]


# Creates (or re-arms) an invite for an email and emails the signup link. Returns 409 if the email
# already has an account.
@router.post("/invites", response_model=InviteResponse)
@limiter.limit(INVITE_LIMIT)
async def create_invite(
    request: Request, response: Response, body: CreateInviteRequest, admin: AdminUser, session: AdminSessionDep
) -> InviteResponse:
    invite = await invite_service.create_invite(session, body.email, admin.id)
    return _to_response(invite)


# Re-arms an existing invite with a fresh token and re-sends the link. Returns 404 if unknown, 409 if
# it was already accepted.
@router.post("/invites/{invite_id}/resend", response_model=InviteResponse)
@limiter.limit(INVITE_LIMIT)
async def resend_invite(request: Request, response: Response, invite_id: int, admin: AdminUser, session: AdminSessionDep) -> InviteResponse:
    invite = await invite_service.resend_invite(session, invite_id)
    return _to_response(invite)


# Revokes a pending invite so its link no longer works. Returns 404 if unknown, 409 if it was already
# accepted (the account exists; nothing to revoke).
@router.post("/invites/{invite_id}/revoke", response_model=InviteResponse)
async def revoke_invite(invite_id: int, admin: AdminUser, session: AdminSessionDep) -> InviteResponse:
    invite = await invite_service.revoke_invite(session, invite_id)
    return _to_response(invite)
