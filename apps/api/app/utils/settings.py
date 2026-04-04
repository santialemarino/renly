# Shared setting helpers used by multiple routers.

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import user_settings_repository
from app.services.settings_service import DOLLAR_RATE_DEFAULT, SETTINGS_KEY_DOLLAR_RATE_PREFERENCE


# Reads the user's dollar rate preference from settings. Returns default if not set.
async def get_dollar_pref(session: AsyncSession, user_id: int) -> str:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    if row and row.settings:
        pref = row.settings.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
        if isinstance(pref, str) and pref:
            return pref
    return DOLLAR_RATE_DEFAULT
