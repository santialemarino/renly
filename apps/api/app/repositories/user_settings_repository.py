# Data access for user settings.

from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user_settings import UserSettings


# Returns {user_id: timezone_name} for every user that has a non-empty 'timezone' key in their settings.
# Users without a stored timezone are omitted; callers fall back to UTC.
async def get_all_timezones(session: AsyncSession) -> dict[int, str]:
    result = await session.execute(select(UserSettings.user_id, UserSettings.settings))
    out: dict[int, str] = {}
    for user_id, settings in result.all():
        tz = settings.get("timezone") if isinstance(settings, dict) else None
        if isinstance(tz, str) and tz:
            out[user_id] = tz
    return out


# Fetches settings row by user_id. Returns None if not found.
async def get_by_user_id(
    session: AsyncSession,
    user_id: int,
) -> UserSettings | None:
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id),
    )
    return result.scalar_one_or_none()


# Persists a new settings row and flushes to get the id.
async def create(
    session: AsyncSession,
    user_settings: UserSettings,
) -> UserSettings:
    session.add(user_settings)
    await session.flush()
    return user_settings


# Persists changes to an existing settings row.
async def save(session: AsyncSession, user_settings: UserSettings) -> None:
    session.add(user_settings)


# Latches a single boolean settings flag to True via a targeted JSONB merge upsert (never a
# read-modify-write of the whole blob) so it can't clobber a concurrent settings write, and works
# whether or not a settings row exists yet. Idempotent; does NOT commit — the caller's transaction
# persists it.
async def latch_flag(session: AsyncSession, user_id: int, key: str) -> None:
    marker = {key: True}
    stmt = (
        insert(UserSettings)
        .values(user_id=user_id, settings=marker)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={"settings": UserSettings.__table__.c.settings.op("||")(cast(marker, JSONB))},
        )
    )
    await session.execute(stmt)


# Namespace to call repository functions (e.g. user_settings_repository.get_by_user_id).
class UserSettingsRepository:
    create = staticmethod(create)
    get_all_timezones = staticmethod(get_all_timezones)
    get_by_user_id = staticmethod(get_by_user_id)
    latch_flag = staticmethod(latch_flag)
    save = staticmethod(save)


# Singleton used by services to access user_settings persistence.
user_settings_repository = UserSettingsRepository()
