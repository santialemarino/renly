# Rotating refresh tokens for silent access-token renewal (AUTH-7 "remember me"). One is issued
# alongside the access token at login and rotated single-use on every /auth/refresh. All flows run on
# the privileged session — like the auth_tokens flows, /auth/refresh is pre-auth (the caller presents
# a refresh token, not an access token), so the lookup must bypass RLS.

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain import InvalidRefreshTokenError
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import refresh_token_repository, user_repository

# A rotated (consumed) token may be re-presented within this window without tripping reuse detection.
# It absorbs the benign races inherent to NextAuth on the App Router: middleware refreshes the token
# for the response while the same request's RSC tree still holds the pre-rotation cookie, so the old
# token is replayed milliseconds later. Re-presentation after the window is treated as theft.
REUSE_GRACE = timedelta(seconds=30)


# A freshly minted refresh token: the raw value (returned once, stored only as a hash) and its
# lifetime in seconds (for the client's expiry bookkeeping).
@dataclass
class IssuedRefreshToken:
    raw_token: str
    expires_in: int


# SHA-256 hex of a raw token. The raw value is high-entropy, so a fast hash is sufficient (unlike
# passwords); only the hash is stored, so a DB leak can't reconstruct live tokens.
def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# The (sliding) validity window: the long "remember me" window or the short ordinary-session one.
def _ttl_for(remember_me: bool) -> timedelta:
    if remember_me:
        return timedelta(days=settings.refresh_token_remember_days)
    return timedelta(hours=settings.refresh_token_default_hours)


# Mints one token in a family and persists it (flushes; caller commits). Shared by login (a new
# family) and rotation (the presented token's family). Purges the user's already-expired rows first,
# so the table stays bounded across both flows — even a long-lived "remember me" session that rotates
# for weeks without ever logging in again sheds its expired rows on each rotation. Returns the raw
# token for the client.
async def _mint(session: AsyncSession, user: User, family_id: str, remember_me: bool, now: datetime) -> IssuedRefreshToken:
    await refresh_token_repository.delete_expired_by_user(session, user.id, now)
    ttl = _ttl_for(remember_me)
    raw_token = secrets.token_urlsafe(32)
    token = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        family_id=family_id,
        session_epoch=user.session_epoch,
        remember_me=remember_me,
        expires_at=now + ttl,
    )
    await refresh_token_repository.create(session, token)
    return IssuedRefreshToken(raw_token=raw_token, expires_in=int(ttl.total_seconds()))


# Starts a brand-new refresh-token family for a fresh login and commits. Returns the raw token and
# its lifetime in seconds. (_mint purges the user's already-expired rows.)
async def issue_refresh_token(session: AsyncSession, user: User, remember_me: bool) -> IssuedRefreshToken:
    now = utcnow()
    issued = await _mint(session, user, uuid.uuid4().hex, remember_me, now)
    await session.commit()
    return issued


# Exchanges a valid refresh token for the next one in its family (rotation) and returns the owning
# user so the caller can mint a fresh access token. Single-use: the presented token is consumed and
# its successor minted in the same family. Re-presenting a consumed token within REUSE_GRACE is a
# benign race (returns a fresh rotation); beyond the window it is treated as theft and revokes the
# whole family. Raises InvalidRefreshTokenError when the token is unknown, expired, revoked, reused,
# or its session_epoch no longer matches the user (logout / password change / reset).
async def rotate_refresh_token(session: AsyncSession, raw_token: str) -> tuple[User, IssuedRefreshToken]:
    now = utcnow()
    token = await refresh_token_repository.get_by_hash(session, _hash_token(raw_token))
    if token is None or token.revoked_at is not None or token.expires_at < now:
        raise InvalidRefreshTokenError()

    if token.consumed_at is not None:
        # Already rotated. Within the grace window this is a benign replay; beyond it, token theft.
        if now - token.consumed_at > REUSE_GRACE:
            await refresh_token_repository.revoke_family(session, token.family_id, now)
            await session.commit()
            raise InvalidRefreshTokenError()
        return await _rotate(session, token, now)

    return await _rotate(session, token, now, consume=True)


# Validates the owning user's epoch, consumes the presented token when it is the active head, mints
# the successor, and commits. Shared by the normal and grace-window paths.
async def _rotate(session: AsyncSession, token: RefreshToken, now: datetime, consume: bool = False) -> tuple[User, IssuedRefreshToken]:
    user = await user_repository.get_by_id(session, token.user_id)
    if user is None or user.session_epoch != token.session_epoch:
        raise InvalidRefreshTokenError()
    if consume:
        token.consumed_at = now
        await refresh_token_repository.save(session, token)
    issued = await _mint(session, user, token.family_id, token.remember_me, now)
    await session.commit()
    return user, issued
