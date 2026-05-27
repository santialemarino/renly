# Shared setting helpers used by multiple routers.

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import user_settings_repository
from app.services.settings_service import (
    DOLLAR_RATE_DEFAULT,
    SETTINGS_KEY_DOLLAR_RATE_PREFERENCE,
    SETTINGS_KEY_LIQUIDITY_THRESHOLD_PCT,
)
from app.utils.liquidity import DEFAULT_LIQUIDITY_THRESHOLD_PCT


# Reads the user's dollar rate preference from settings. Returns default if not set.
async def get_dollar_pref(session: AsyncSession, user_id: int) -> str:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    if row and row.settings:
        pref = row.settings.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
        if isinstance(pref, str) and pref:
            return pref
    return DOLLAR_RATE_DEFAULT


# Reads the user's liquidity-alert threshold from settings. Returns the backend default
# when unset or invalid. Range is enforced server-side via the SettingsUpdate validator.
async def get_liquidity_threshold(session: AsyncSession, user_id: int) -> int:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    if row and row.settings:
        value = row.settings.get(SETTINGS_KEY_LIQUIDITY_THRESHOLD_PCT)
        if isinstance(value, int) and 1 <= value <= 99:
            return value
    return DEFAULT_LIQUIDITY_THRESHOLD_PCT
