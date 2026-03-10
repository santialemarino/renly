from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user_settings import UserSettings


# Fetches settings row by user_id. Returns None if not found.
async def get_by_user_id(
    session: AsyncSession,
    user_id: int,
) -> UserSettings | None:
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id),
    )
    return result.scalar_one_or_none()


# Persists settings, commits, refreshes, and returns it (with id set).
async def create(
    session: AsyncSession,
    user_settings: UserSettings,
) -> UserSettings:
    session.add(user_settings)
    await session.commit()
    await session.refresh(user_settings)
    return user_settings


# Persists changes to an existing settings row.
async def save(session: AsyncSession, user_settings: UserSettings) -> None:
    session.add(user_settings)
    await session.commit()


# Namespace to call repository functions (e.g. user_settings_repository.get_by_user_id).
class UserSettingsRepository:
    create = staticmethod(create)
    get_by_user_id = staticmethod(get_by_user_id)
    save = staticmethod(save)


# Singleton used by services to access user_settings persistence.
user_settings_repository = UserSettingsRepository()
