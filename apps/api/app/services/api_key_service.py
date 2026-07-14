import asyncio
import secrets

from bcrypt import checkpw, gensalt, hashpw
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.api_key import ApiKey
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import api_key_repository, user_repository

KEY_PREFIX_LENGTH = 8


# List all active API keys for a user.
async def list_keys(session: AsyncSession, user: User) -> list[ApiKey]:
    return await api_key_repository.list_by_user(session, user.id)


# Generate a new API key. Returns the model and the raw key (shown once).
async def create_key(
    session: AsyncSession,
    user: User,
    *,
    name: str | None = None,
) -> tuple[ApiKey, str]:
    raw_key = secrets.token_urlsafe(32)
    key_hash = (await asyncio.to_thread(hashpw, raw_key.encode(), gensalt())).decode()
    key = ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=raw_key[:KEY_PREFIX_LENGTH],
        name=name,
    )
    key = await api_key_repository.create(session, key)
    await session.commit()
    return key, raw_key


# Revoke an API key (soft-delete by setting is_active = False).
async def revoke_key(session: AsyncSession, key_id: int, user: User) -> None:
    key = await api_key_repository.get_by_id(session, key_id, user.id)
    if key is None:
        raise NotFoundError("API key not found.")
    key.is_active = False
    await api_key_repository.save(session, key)
    await session.commit()


# Verify a raw API key. Uses prefix index to narrow candidates, then bcrypt (run in a worker
# thread — each checkpw is ~250ms of CPU that must not block the event loop).
async def verify_api_key(session: AsyncSession, raw_key: str) -> User | None:
    prefix = raw_key[:KEY_PREFIX_LENGTH]
    candidates = await api_key_repository.list_active_by_prefix(session, prefix)
    # Release the admin-pool connection before the ~250ms threaded bcrypt per candidate: this runs
    # on the shared admin pool (pre-auth, no user context), so holding a connection across the hash
    # would let an API-key burst exhaust it and queue on pool_timeout. The last-used update below
    # re-acquires; expire_on_commit=False keeps the candidate rows usable without a reload.
    await session.commit()
    for key in candidates:
        if await asyncio.to_thread(checkpw, raw_key.encode(), key.key_hash.encode()):
            key.last_used_at = utcnow()
            await api_key_repository.save(session, key)
            await session.commit()
            user = await user_repository.get_by_id(session, key.user_id)
            return user
    return None
