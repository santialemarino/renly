# Data access for rotating refresh tokens (AUTH-7).

from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.refresh_token import RefreshToken


# Fetches a refresh token by its SHA-256 hash. Returns None when no token matches.
async def get_by_hash(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    return result.scalar_one_or_none()


# Persists a new token and flushes to get the id.
async def create(session: AsyncSession, token: RefreshToken) -> RefreshToken:
    session.add(token)
    await session.flush()
    return token


# Persists changes to an existing token (e.g. marking it consumed).
async def save(session: AsyncSession, token: RefreshToken) -> None:
    session.add(token)


# Revokes every still-active token in a family at once — reuse detection kills the whole lineage.
async def revoke_family(session: AsyncSession, family_id: str, revoked_at: datetime) -> None:
    await session.execute(
        sa_update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=revoked_at)
    )


# Deletes a user's already-expired tokens, keeping the table from growing across logins (hygiene).
async def delete_expired_by_user(session: AsyncSession, user_id: int, now: datetime) -> None:
    await session.execute(sa_delete(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.expires_at < now))


# Namespace to call repository functions (e.g. refresh_token_repository.get_by_hash).
class RefreshTokenRepository:
    create = staticmethod(create)
    delete_expired_by_user = staticmethod(delete_expired_by_user)
    get_by_hash = staticmethod(get_by_hash)
    revoke_family = staticmethod(revoke_family)
    save = staticmethod(save)


# Singleton used by services to access refresh-token persistence.
refresh_token_repository = RefreshTokenRepository()
