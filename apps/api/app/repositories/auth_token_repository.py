# Data access for single-use account-lifecycle tokens (AUTH-1/2/8).

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.auth_token import AuthToken, AuthTokenType


# Fetches a token by its SHA-256 hash. Returns None when no token matches.
async def get_by_hash(session: AsyncSession, token_hash: str) -> AuthToken | None:
    result = await session.execute(select(AuthToken).where(AuthToken.token_hash == token_hash))
    return result.scalar_one_or_none()


# Persists a new token and flushes to get the id.
async def create(session: AsyncSession, token: AuthToken) -> AuthToken:
    session.add(token)
    await session.flush()
    return token


# Persists changes to an existing token (e.g. marking it consumed).
async def save(session: AsyncSession, token: AuthToken) -> None:
    session.add(token)


# Deletes all of a user's unconsumed tokens of a type, so issuing a fresh one invalidates the old.
async def delete_unconsumed_by_user_type(session: AsyncSession, user_id: int, token_type: AuthTokenType) -> None:
    await session.execute(
        sa_delete(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.token_type == token_type,
            AuthToken.consumed_at.is_(None),
        )
    )


# Namespace to call repository functions (e.g. auth_token_repository.get_by_hash).
class AuthTokenRepository:
    create = staticmethod(create)
    delete_unconsumed_by_user_type = staticmethod(delete_unconsumed_by_user_type)
    get_by_hash = staticmethod(get_by_hash)
    save = staticmethod(save)


# Singleton used by services to access auth-token persistence.
auth_token_repository = AuthTokenRepository()
