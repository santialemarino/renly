from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.api_key import ApiKey


# List all active API keys for a user.
async def list_by_user(session: AsyncSession, user_id: int) -> list[ApiKey]:
    result = await session.execute(select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.is_active.is_(True)).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


# Get a single API key by id and user_id.
async def get_by_id(session: AsyncSession, key_id: int, user_id: int) -> ApiKey | None:
    result = await session.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    return result.scalar_one_or_none()


# Find active keys matching a prefix (first 8 chars of the raw key). Narrows bcrypt search.
async def list_active_by_prefix(session: AsyncSession, prefix: str) -> list[ApiKey]:
    result = await session.execute(select(ApiKey).where(ApiKey.is_active.is_(True), ApiKey.key_prefix == prefix))
    return list(result.scalars().all())


# Insert a new API key.
async def create(session: AsyncSession, key: ApiKey) -> ApiKey:
    session.add(key)
    await session.flush()
    return key


# Stage an API key for update (caller commits).
async def save(session: AsyncSession, key: ApiKey) -> None:
    session.add(key)


# Namespace to call repository functions (e.g. api_key_repository.list_by_user).
class ApiKeyRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    list_active_by_prefix = staticmethod(list_active_by_prefix)
    create = staticmethod(create)
    save = staticmethod(save)


# Singleton used by services to access API key persistence.
api_key_repository = ApiKeyRepository()
