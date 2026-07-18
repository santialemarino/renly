# Admin invites for the invite-only access gate. An admin creates one invite per email; the invited
# address gets a signup link carrying a single-use, time-limited token (the same SHA-256 / single-use
# pattern as auth_tokens — only the hash is stored). Registration consumes it (auth_service gates
# POST /auth/register on a valid invite in invite mode). Every flow here runs on the privileged
# session: admin reads span all invites, and the register/signup-context lookups are pre-auth — so
# the per-user RLS policy on invites is defense-in-depth, not the gate (is_admin at the endpoint is).

import hashlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain import InvalidInviteError, InviteEmailTakenError, NotFoundError
from app.models.invite import Invite, InviteStatus
from app.models.utils import utcnow
from app.repositories import invite_repository, user_repository
from app.services import email_templates, settings_service
from app.services.email_service import EmailMessage, get_email_service

logger = logging.getLogger(__name__)

# How long an invite link stays valid; resend rotates the token and restarts this window.
INVITE_TOKEN_TTL = timedelta(days=7)

# Web route the invite link points at (resolved against settings.web_base_url).
_SIGNUP_PATH = "/signup"


# SHA-256 hex of a raw token. The raw value is high-entropy, so a fast hash is sufficient (unlike
# passwords); only the hash is stored, so a DB leak can't reconstruct live invite links.
def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# Builds the absolute signup link carrying the raw invite token as a query param.
def _invite_link(raw_token: str) -> str:
    return f"{settings.web_base_url}{_SIGNUP_PATH}?invite={raw_token}"


# Sends an email without letting a provider failure surface to the caller — the invite is already
# committed, so a send outage shouldn't fail the request; the admin can resend it.
async def _safe_send(message: EmailMessage) -> None:
    try:
        await get_email_service().send(message)
    except Exception:
        logger.warning("Failed to send '%s' email to %s.", message.subject, message.to, exc_info=True)


# The effective status shown to admins: a pending invite past its expiry reads as "expired" (derived,
# not stored — resend simply restarts the window).
def effective_status(invite: Invite) -> str:
    if invite.status == InviteStatus.pending and invite.expires_at < utcnow():
        return "expired"
    return invite.status.value


# Lists every invite, newest first (admin invite management view).
async def list_invites(session: AsyncSession) -> list[Invite]:
    return await invite_repository.list_all(session)


# Creates (or re-arms) an invite for an email and emails the signup link. Rejects an address that
# already has an account (InviteEmailTakenError). One invite per email: an existing invite for the
# address is rotated to a fresh token and a restarted window rather than duplicated. Commits, then
# sends. Returns the stored invite (the raw token lives only in the email).
async def create_invite(session: AsyncSession, email: str, invited_by_id: int) -> Invite:
    email = email.lower()
    if await user_repository.get_by_email(session, email) is not None:
        raise InviteEmailTakenError()

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = utcnow() + INVITE_TOKEN_TTL
    invite = await invite_repository.get_by_email(session, email)
    if invite is None:
        invite = Invite(email=email, token_hash=token_hash, invited_by=invited_by_id, status=InviteStatus.pending, expires_at=expires_at)
        await invite_repository.create(session, invite)
    else:
        invite.token_hash = token_hash
        invite.invited_by = invited_by_id
        invite.status = InviteStatus.pending
        invite.consumed_at = None
        invite.expires_at = expires_at
        await invite_repository.save(session, invite)
    await session.commit()
    locale = await settings_service.get_user_language(session, invited_by_id)
    await _safe_send(email_templates.invite_email(email, _invite_link(raw_token), locale=locale))
    return invite


# Re-arms an existing invite with a fresh token and a restarted window, then re-sends the link.
# Raises NotFoundError when the id is unknown, InviteEmailTakenError when it was already accepted.
async def resend_invite(session: AsyncSession, invite_id: int) -> Invite:
    invite = await invite_repository.get_by_id(session, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found.")
    if invite.status == InviteStatus.accepted:
        raise InviteEmailTakenError()

    raw_token = secrets.token_urlsafe(32)
    invite.token_hash = _hash_token(raw_token)
    invite.status = InviteStatus.pending
    invite.consumed_at = None
    invite.expires_at = utcnow() + INVITE_TOKEN_TTL
    await invite_repository.save(session, invite)
    await session.commit()
    locale = await settings_service.get_user_language(session, invite.invited_by)
    await _safe_send(email_templates.invite_email(invite.email, _invite_link(raw_token), locale=locale))
    return invite


# Revokes a pending invite so its link no longer works. Raises NotFoundError when the id is unknown,
# InviteEmailTakenError when it was already accepted (the account exists; nothing to revoke).
async def revoke_invite(session: AsyncSession, invite_id: int) -> Invite:
    invite = await invite_repository.get_by_id(session, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found.")
    if invite.status == InviteStatus.accepted:
        raise InviteEmailTakenError()

    invite.status = InviteStatus.revoked
    await invite_repository.save(session, invite)
    await session.commit()
    return invite


# Returns the pending, unexpired invite for a raw token, or None (unknown / not pending / expired).
# Does not check the email — used by the signup-context lookup, which resolves the email to lock.
async def get_pending_invite_by_token(session: AsyncSession, raw_token: str | None) -> Invite | None:
    if not raw_token:
        return None
    invite = await invite_repository.get_by_hash(session, _hash_token(raw_token))
    if invite is None or invite.status != InviteStatus.pending or invite.expires_at < utcnow():
        return None
    return invite


# Validates an invite for registration: the token must resolve to a pending, unexpired invite whose
# email matches the registering address. Raises InvalidInviteError otherwise. Caller consumes it.
async def get_valid_invite(session: AsyncSession, raw_token: str | None, email: str) -> Invite:
    invite = await get_pending_invite_by_token(session, raw_token)
    if invite is None or invite.email != email.lower():
        raise InvalidInviteError()
    return invite


# Marks an invite accepted (single-use) once registration succeeds. Flushes via save; the caller
# (register) commits in the same transaction as the new account.
async def consume_invite(session: AsyncSession, invite: Invite) -> None:
    invite.status = InviteStatus.accepted
    invite.consumed_at = utcnow()
    await invite_repository.save(session, invite)
