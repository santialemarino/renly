from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_settings import UserSettings
from app.repositories import user_settings_repository

SETTINGS_KEY_PRIMARY = "primary_currency"
SETTINGS_KEY_SECONDARY = "secondary_currency"

_NOT_SET = object()


def _settings_to_response(settings: dict) -> dict:
    raw_primary = settings.get(SETTINGS_KEY_PRIMARY)
    primary_currency = raw_primary if isinstance(raw_primary, str) and raw_primary else None
    raw_secondary = settings.get(SETTINGS_KEY_SECONDARY)
    secondary_currency = raw_secondary if isinstance(raw_secondary, str) and raw_secondary else None
    return {
        "primary_currency": primary_currency,
        "secondary_currency": secondary_currency,
    }


# Returns current user's settings. Returns nulls when no row or missing keys.
async def get_settings(
    session: AsyncSession,
    user: User,
) -> dict:
    row = await user_settings_repository.get_by_user_id(session, user.id)
    if row is None:
        return _settings_to_response({})
    return _settings_to_response(row.settings)


# Updates settings (partial merge). Creates row if missing. Returns updated settings.
async def update_settings(
    session: AsyncSession,
    user: User,
    primary_currency: str | None = _NOT_SET,
    secondary_currency: str | None = _NOT_SET,
) -> dict:
    row = await user_settings_repository.get_by_user_id(session, user.id)
    if row is None:
        row = UserSettings(user_id=user.id, settings={})
        row = await user_settings_repository.create(session, row)
    settings = dict(row.settings)
    if primary_currency is not _NOT_SET:
        settings[SETTINGS_KEY_PRIMARY] = primary_currency
    if secondary_currency is not _NOT_SET:
        settings[SETTINGS_KEY_SECONDARY] = secondary_currency
    row.settings = settings
    await user_settings_repository.save(session, row)
    await session.refresh(row)
    return _settings_to_response(row.settings)
