from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment import Currency
from app.models.user import User
from app.models.user_settings import UserSettings
from app.repositories import user_settings_repository

DEFAULT_DISPLAY_CURRENCIES: list[Currency] = [Currency.ARS, Currency.USD]
SETTINGS_KEY_DISPLAY = "display_currencies"
SETTINGS_KEY_DEFAULT = "default_currency"

_NOT_SET = object()


def _settings_to_response(settings: dict) -> dict:
    raw_display = settings.get(SETTINGS_KEY_DISPLAY)
    display_currencies = (
        [Currency(c) for c in raw_display if c in Currency.__members__]
        if isinstance(raw_display, list)
        else list(DEFAULT_DISPLAY_CURRENCIES)
    )
    if not display_currencies:
        display_currencies = list(DEFAULT_DISPLAY_CURRENCIES)
    raw_default = settings.get(SETTINGS_KEY_DEFAULT)
    default_currency = Currency(raw_default) if raw_default in Currency.__members__ else None
    return {
        "display_currencies": display_currencies,
        "default_currency": default_currency,
    }


# Returns current user's settings. Uses defaults when no row or missing keys.
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
    display_currencies: list[Currency] | None = _NOT_SET,
    default_currency: Currency | None = _NOT_SET,
) -> dict:
    row = await user_settings_repository.get_by_user_id(session, user.id)
    if row is None:
        row = UserSettings(user_id=user.id, settings={})
        row = await user_settings_repository.create(session, row)
    settings = dict(row.settings)
    if display_currencies is not _NOT_SET:
        settings[SETTINGS_KEY_DISPLAY] = [c.value for c in display_currencies]
    if default_currency is not _NOT_SET:
        settings[SETTINGS_KEY_DEFAULT] = default_currency.value if default_currency else None
    row.settings = settings
    await user_settings_repository.save(session, row)
    await session.refresh(row)
    return _settings_to_response(row.settings)
