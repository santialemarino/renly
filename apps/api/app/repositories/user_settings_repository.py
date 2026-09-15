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


# Returns {user_id: language} for the requested users that have a non-empty 'language' key in their
# settings. Users without one are omitted; callers apply the default language.
async def get_languages_by_user_ids(session: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    return await get_string_by_user_ids(session, user_ids, "language")


# Returns {user_id: value} for the requested users holding a non-empty string under `key`. Users
# without one are omitted, so the caller applies its own default rather than this deciding it.
#
# Generic over the key because two callers now need the same shape over the same blob — the language a
# transactional email is written in, and the cadence its recipient asked for — and two copies of this
# loop is two places a settings key can be read one way here and another way there.
async def get_string_by_user_ids(session: AsyncSession, user_ids: list[int], key: str) -> dict[int, str]:
    if not user_ids:
        return {}
    result = await session.execute(
        select(UserSettings.user_id, UserSettings.settings).where(UserSettings.user_id.in_(user_ids)),
    )
    out: dict[int, str] = {}
    for user_id, settings in result.all():
        value = settings.get(key) if isinstance(settings, dict) else None
        if isinstance(value, str) and value:
            out[user_id] = value
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


# Writes a single settings key via a targeted JSONB merge upsert (never a read-modify-write of the
# whole blob) so it can't clobber a concurrent settings write, and works whether or not a settings row
# exists yet. Idempotent; does NOT commit — the caller's transaction persists it.
async def set_key(session: AsyncSession, user_id: int, key: str, value: object) -> None:
    patch = {key: value}
    stmt = (
        insert(UserSettings)
        .values(user_id=user_id, settings=patch)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={"settings": UserSettings.__table__.c.settings.op("||")(cast(patch, JSONB))},
        )
    )
    await session.execute(stmt)


# Latches a single boolean settings flag to True. The one-value case of set_key, kept as its own name
# because every caller means "latch", not "write whatever I pass".
async def latch_flag(session: AsyncSession, user_id: int, key: str) -> None:
    await set_key(session, user_id, key, True)


# Namespace to call repository functions (e.g. user_settings_repository.get_by_user_id).
class UserSettingsRepository:
    create = staticmethod(create)
    get_all_timezones = staticmethod(get_all_timezones)
    get_by_user_id = staticmethod(get_by_user_id)
    get_languages_by_user_ids = staticmethod(get_languages_by_user_ids)
    get_string_by_user_ids = staticmethod(get_string_by_user_ids)
    latch_flag = staticmethod(latch_flag)
    save = staticmethod(save)
    set_key = staticmethod(set_key)


# Singleton used by services to access user_settings persistence.
user_settings_repository = UserSettingsRepository()
