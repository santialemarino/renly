# Group-seat invites (shared money). Reuses the platform invite MECHANISM — a high-entropy raw token
# whose SHA-256 hash is all that is stored, a time-limited window, single-use via consumed_at, and
# rotate-on-resend — while staying a separate entity, because the two mean different things:
#
#   invites (SIGNUP_MODE gate)          group_invites (here)
#   ---------------------------------   -----------------------------------------------------------
#   creates an ACCOUNT                  links an EXISTING account to one group seat
#   globally unique per email           one per seat; the same person may hold seats in many groups
#   token bound to the invited email    the token IS the credential (see below)
#   grants platform access              grants no signup access whatsoever
#
# Why the token alone authorises the claim: nothing is created here, so there is no address for a new
# account to be bound to — the link only says "this seat is yours". Requiring the accepter's account
# email to equal the invited one would add friction with no security (their Renly address is often not
# the one you know) and would make a shareable link impossible, since a link has no email to match.
# So `email` records where the link was sent and constrains nothing. Mitigations are the ones that
# actually apply to a link: single-use, a short window, revocable, and rotated on every resend.
#
# accept_invite runs on the PRIVILEGED session. That is not a shortcut: the person redeeming the token
# is not a member yet, so the membership RLS policy hides the invite row from them, and no widening of
# a WITH CHECK can help a SELECT. Everything else here runs on the request session under RLS.

import hashlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain import GroupMembershipExistsError, InvalidTokenError, NotFoundError
from app.models.group_invite import GroupInvite
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import group_invite_repository, group_repository, user_repository
from app.schemas.group_invite import GroupInviteAcceptedResponse, GroupInviteCreatedResponse, GroupInvitePreviewResponse
from app.services import email_templates, group_service, settings_service
from app.services.email_service import EmailMessage, get_email_service

logger = logging.getLogger(__name__)

# How long an invite link stays valid; a resend rotates the token and restarts this window. Matches the
# platform invite's TTL — the same trade-off between "long enough to actually get opened" and exposure.
GROUP_INVITE_TOKEN_TTL = timedelta(days=7)

# Web route the invite link points at. Deliberately PUBLIC (unauthenticated): most recipients open the
# link while logged out, and a protected landing page would bounce them to login and lose the token.
_JOIN_PATH = "/join"


# SHA-256 hex of a raw token. The raw value is high-entropy, so a fast hash is sufficient (unlike a
# password); only the hash is stored, so a DB leak cannot reconstruct live invite links.
def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# Builds the absolute join link carrying the raw invite token as a query param.
def _invite_link(raw_token: str) -> str:
    return f"{settings.web_base_url}{_JOIN_PATH}?token={raw_token}"


# Sends an email without letting a provider failure surface to the caller — the invite is already
# committed and the link is already in the response, so a send outage shouldn't fail the request.
async def _safe_send(message: EmailMessage) -> None:
    try:
        await get_email_service().send(message)
    except Exception:
        logger.warning("Failed to send '%s' email to %s.", message.subject, message.to, exc_info=True)


# Resolves a raw token to its invite, or raises InvalidTokenError for anything a user cannot act on:
# unknown, already claimed, or past its window. One error for all three on purpose — telling a holder
# WHICH it was would let them probe tokens, and the remedy ("ask for a new link") is the same.
async def _require_live_invite(admin_session: AsyncSession, raw_token: str) -> GroupInvite:
    invite = await group_invite_repository.get_by_hash(admin_session, _hash_token(raw_token))
    if invite is None or invite.consumed_at is not None or invite.expires_at <= utcnow():
        raise InvalidTokenError()
    return invite


# Creates the seat's invite, or rotates an existing one (a resend), and emails the link when an address
# is given. Admin only. Returns the raw link — the ONLY time it exists outside the email, since nothing
# stores it. A link-only invite (no email) is the shareable-link half of D7: the caller shares it.
async def create_invite(
    session: AsyncSession,
    group_id: int,
    member_id: int,
    user: User,
    *,
    email: str | None = None,
) -> GroupInviteCreatedResponse:
    group, _ = await group_service.require_admin(session, group_id, user)
    member = await group_repository.get_member(session, group.id, member_id)
    if member is None or not member.is_active:
        raise NotFoundError("Group member not found")
    # A seat someone already holds has nothing to claim, and re-inviting it would mint a token that
    # could only ever fail. The supported move is to remove that member first.
    if member.user_id is not None:
        raise GroupMembershipExistsError()

    normalized_email = email.lower() if email else None
    raw_token = secrets.token_urlsafe(32)
    expires_at = utcnow() + GROUP_INVITE_TOKEN_TTL
    invite = await group_invite_repository.get_by_member(session, member.id)
    if invite is None:
        invite = GroupInvite(
            group_id=group.id,
            member_id=member.id,
            email=normalized_email,
            token_hash=_hash_token(raw_token),
            expires_at=expires_at,
            created_by=user.id,
        )
        await group_invite_repository.create(session, invite)
    else:
        # Rotate in place: the previous link dies immediately, which is what makes a resend safe.
        invite.email = normalized_email
        invite.token_hash = _hash_token(raw_token)
        invite.expires_at = expires_at
        invite.consumed_at = None
        invite.created_by = user.id
        await group_invite_repository.save(session, invite)
    await session.commit()

    link = _invite_link(raw_token)
    if normalized_email:
        # Localized to the SENDER's language: the recipient may not have an account, so there is no
        # stored preference to read.
        locale = await settings_service.get_user_language(session, user.id)
        await _safe_send(email_templates.group_invite_email(normalized_email, link, group.name, user.name, locale=locale))
    return GroupInviteCreatedResponse(member_id=member.id, email=normalized_email, invite_url=link, expires_at=expires_at)


# Revokes a seat's invite by deleting the row, so the link stops working immediately and the seat stays
# the name-only member it already was. Admin only. Idempotent: revoking nothing is not an error, since
# the caller's intent ("this link must not work") is satisfied either way.
async def revoke_invite(session: AsyncSession, group_id: int, member_id: int, user: User) -> None:
    group, _ = await group_service.require_admin(session, group_id, user)
    member = await group_repository.get_member(session, group.id, member_id)
    if member is None:
        raise NotFoundError("Group member not found")
    await group_invite_repository.delete_by_member(session, member.id)
    await session.commit()


# The pre-membership preview behind a join link: what the recipient needs in order to decide, and
# nothing else. Unauthenticated, and runs on the privileged session because the reader is not a member
# yet. It carries no financial data and no other member's identity — only the group's name and kind,
# the seat's own label, and who sent it.
async def preview_invite(admin_session: AsyncSession, raw_token: str) -> GroupInvitePreviewResponse:
    invite = await _require_live_invite(admin_session, raw_token)
    group = await group_repository.get_by_id(admin_session, invite.group_id)
    member = await group_repository.get_member(admin_session, invite.group_id, invite.member_id)
    if group is None or member is None:
        raise InvalidTokenError()
    inviter = await user_repository.get_by_id(admin_session, invite.created_by) if invite.created_by else None
    return GroupInvitePreviewResponse(
        group_name=group.name,
        group_kind=group.kind,
        member_display_name=member.display_name,
        invited_by_name=inviter.name if inviter else None,
        expires_at=invite.expires_at,
    )


# Claims the seat for the calling account: links it, stamps joined_at, and consumes the invite — one
# transaction, on the privileged session (see the module comment). Raises InvalidTokenError for a link
# that is not live or whose seat is no longer claimable, and GroupMembershipExistsError when the caller
# already holds a seat in that group (one person is one member per group, which is what makes a member
# id a usable counterparty).
async def accept_invite(admin_session: AsyncSession, raw_token: str, user: User) -> GroupInviteAcceptedResponse:
    invite = await _require_live_invite(admin_session, raw_token)
    group = await group_repository.get_by_id(admin_session, invite.group_id)
    member = await group_repository.get_member(admin_session, invite.group_id, invite.member_id)
    # A seat that was deactivated or already linked after the link was sent cannot be claimed.
    # remove_member deletes the pending invite, so reaching this is defence in depth, not the path.
    if group is None or member is None or not member.is_active or member.user_id is not None:
        raise InvalidTokenError()
    existing = await group_repository.get_member_by_user(admin_session, invite.group_id, user.id)
    if existing is not None:
        raise GroupMembershipExistsError()

    member.user_id = user.id
    member.joined_at = utcnow()
    await group_repository.save_member(admin_session, member)
    invite.consumed_at = utcnow()
    await group_invite_repository.save(admin_session, invite)
    await admin_session.commit()
    return GroupInviteAcceptedResponse(group_id=group.id, group_name=group.name, member_id=member.id)
