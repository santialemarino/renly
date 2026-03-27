from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_settings import UserSettings
from app.repositories import user_settings_repository

SETTINGS_KEY_PRIMARY = "primary_currency"
SETTINGS_KEY_SECONDARY = "secondary_currency"
SETTINGS_KEY_PREFERRED_CURRENCIES = "preferred_currencies"
SETTINGS_KEY_PERIOD_PRESETS = "period_presets"
SETTINGS_KEY_MAX_GROUPS = "max_groups"
SETTINGS_KEY_GROUP_WARNING_PCT = "group_warning_pct"
SETTINGS_KEY_DOLLAR_RATE_PREFERENCE = "dollar_rate_preference"

# Valid values for dollar rate preference.
DOLLAR_RATE_DEFAULT = "mep"

_NOT_SET = object()


def _settings_to_response(settings: dict) -> dict:
    raw_primary = settings.get(SETTINGS_KEY_PRIMARY)
    primary_currency = raw_primary if isinstance(raw_primary, str) and raw_primary else None
    raw_secondary = settings.get(SETTINGS_KEY_SECONDARY)
    secondary_currency = raw_secondary if isinstance(raw_secondary, str) and raw_secondary else None
    raw_preferred = settings.get(SETTINGS_KEY_PREFERRED_CURRENCIES)
    preferred_currencies = raw_preferred if isinstance(raw_preferred, list) else None
    raw_presets = settings.get(SETTINGS_KEY_PERIOD_PRESETS)
    period_presets = raw_presets if isinstance(raw_presets, list) else None
    raw_max_groups = settings.get(SETTINGS_KEY_MAX_GROUPS)
    max_groups = raw_max_groups if isinstance(raw_max_groups, int) else None
    raw_warning_pct = settings.get(SETTINGS_KEY_GROUP_WARNING_PCT)
    group_warning_pct = raw_warning_pct if isinstance(raw_warning_pct, int) else None
    raw_dollar_pref = settings.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
    dollar_rate_preference = raw_dollar_pref if isinstance(raw_dollar_pref, str) and raw_dollar_pref else None
    return {
        "primary_currency": primary_currency,
        "secondary_currency": secondary_currency,
        "preferred_currencies": preferred_currencies,
        "period_presets": period_presets,
        "max_groups": max_groups,
        "group_warning_pct": group_warning_pct,
        "dollar_rate_preference": dollar_rate_preference,
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
    preferred_currencies: list[str] | None = _NOT_SET,
    period_presets: list[str] | None = _NOT_SET,
    max_groups: int | None = _NOT_SET,
    group_warning_pct: int | None = _NOT_SET,
    dollar_rate_preference: str | None = _NOT_SET,
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
    if preferred_currencies is not _NOT_SET:
        settings[SETTINGS_KEY_PREFERRED_CURRENCIES] = preferred_currencies
    if period_presets is not _NOT_SET:
        settings[SETTINGS_KEY_PERIOD_PRESETS] = period_presets
    if max_groups is not _NOT_SET:
        settings[SETTINGS_KEY_MAX_GROUPS] = max_groups
    if group_warning_pct is not _NOT_SET:
        settings[SETTINGS_KEY_GROUP_WARNING_PCT] = group_warning_pct
    if dollar_rate_preference is not _NOT_SET:
        settings[SETTINGS_KEY_DOLLAR_RATE_PREFERENCE] = dollar_rate_preference
    row.settings = settings
    await user_settings_repository.save(session, row)
    await session.refresh(row)
    return _settings_to_response(row.settings)
