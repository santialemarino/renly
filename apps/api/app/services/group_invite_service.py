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
from app.domain import GroupMembershipExistsError, GroupSeatTakenError, InvalidTokenError, NotFoundError
from app.models.group_invite import GroupInvite
from app.models.notification import NotificationEvent
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import group_invite_repository, group_repository, user_repository
from app.schemas.group_invite import GroupInviteAcceptedResponse, GroupInviteCreatedResponse, GroupInvitePreviewResponse
from app.services import email_templates, group_service, notification_service, settings_service, shared_audit_service
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
# `lock` is passed by the claim path only: see get_by_hash for why a shareable link needs it.
async def _require_live_invite(admin_session: AsyncSession, raw_token: str, *, lock: bool = False) -> GroupInvite:
    invite = await group_invite_repository.get_by_hash(admin_session, _hash_token(raw_token), for_update=lock)
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
    group, inviter = await group_service.require_admin(session, group_id, user)
    member = await group_repository.get_member(session, group.id, member_id)
    if member is None or not member.is_active:
        raise NotFoundError("Group member not found")
    # A seat someone already holds has nothing to claim, and re-inviting it would mint a token that
    # could only ever fail. The supported move is to remove that member first. Deliberately NOT
    # GroupMembershipExistsError: that one tells the CALLER "you are already a member", which is the
    # wrong sentence entirely for an admin inviting somebody else.
    if member.user_id is not None:
        raise GroupSeatTakenError()

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
    # Resolved BEFORE the commit, deliberately: a failure reading the roster then fails the whole use
    # case with nothing written, rather than 500-ing a request whose invite has already landed. After
    # the commit only dispatch() runs, and that swallows everything.
    await shared_audit_service.record(
        session,
        group_id=group.id,
        actor=user,
        entity_type=AuditEntityType.group_invite,
        action=AuditAction.created,
        entity_id=invite.id,
        # The seat's name and nothing else — never the address and never the link. The address belongs
        # to the invitee, and the raw token is the one value token_hash exists to keep out of readable
        # data, since an entry here is readable by every member of the group.
        payload={"member": member.display_name},
    )
    recipients = await group_service.list_notifiable_user_ids(session, group.id, exclude_user_id=user.id)
    await session.commit()

    link = _invite_link(raw_token)
    if normalized_email:
        # Localized to the SENDER's language: the recipient may not have an account, so there is no
        # stored preference to read.
        locale = await settings_service.get_user_language(session, user.id)
        await _safe_send(email_templates.group_invite_email(normalized_email, link, group.name, user.name, locale=locale))

    # The group's OTHER members are told an invite went out — never the invitee, whose only usable
    # channel is the email above. A notification row is readable data and could therefore never carry
    # the raw token, which is precisely what token_hash exists to prevent; a feed entry announcing a
    # link it cannot hand over would be worse than none. So this is group activity, exactly like
    # member_joined beside it.
    await notification_service.dispatch(
        NotificationEvent.group_invited,
        recipients,
        # Both people are named by their SEAT, never by an account name. Inside a group that is the
        # identity everyone else knows — it is what `display_name` is for, and GroupMemberResponse
        # deliberately exposes nothing else — so mixing the two would put two vocabularies in one feed.
        {"group_id": group.id, "group": group.name, "inviter": inviter.display_name, "invitee": member.display_name},
    )
    return GroupInviteCreatedResponse(member_id=member.id, email=normalized_email, invite_url=link, expires_at=expires_at)


# Revokes a seat's invite by deleting the row, so the link stops working immediately and the seat stays
# the name-only member it already was. Admin only. Idempotent: revoking nothing is not an error, since
# the caller's intent ("this link must not work") is satisfied either way.
async def revoke_invite(session: AsyncSession, group_id: int, member_id: int, user: User) -> None:
    group, _ = await group_service.require_admin(session, group_id, user)
    member = await group_repository.get_member(session, group.id, member_id)
    if member is None:
        raise NotFoundError("Group member not found")
    invite = await group_invite_repository.get_by_member(session, member.id)
    await group_invite_repository.delete_by_member(session, member.id)
    # Only when there WAS one. Revoking is idempotent — the caller's intent is satisfied either way —
    # and an entry saying somebody revoked nothing is a line in the trail that describes no act.
    if invite is not None:
        await shared_audit_service.record(
            session,
            group_id=group.id,
            actor=user,
            entity_type=AuditEntityType.group_invite,
            action=AuditAction.revoked,
            entity_id=invite.id,
            payload={"member": member.display_name},
        )
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
    invite = await _require_live_invite(admin_session, raw_token, lock=True)
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
    # Resolved before the commit for the reason create_invite states. Excluding the joiner by ACCOUNT
    # rather than by seat is what makes this correct either side of the commit: their own seat is the
    # one being linked, so filtering on the seat would depend on whether the write had landed yet.
    await shared_audit_service.record(
        admin_session,
        group_id=group.id,
        actor=user,
        entity_type=AuditEntityType.group_member,
        action=AuditAction.joined,
        entity_id=member.id,
        payload={"member": member.display_name},
    )
    recipients = await group_service.list_notifiable_user_ids(admin_session, group.id, exclude_user_id=user.id)
    await admin_session.commit()

    # Everybody else in the group learns the seat is now a real person.
    await notification_service.dispatch(
        NotificationEvent.member_joined,
        recipients,
        {"group_id": group.id, "group": group.name, "member": member.display_name},
    )
    return GroupInviteAcceptedResponse(group_id=group.id, group_name=group.name, member_id=member.id)
