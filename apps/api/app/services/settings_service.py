from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_settings import UserSettings
from app.repositories import user_settings_repository
from app.schemas.settings import LANGUAGE_MODE_VALUES, SUPPORTED_LANGUAGES, TIMEZONE_MODE_VALUES

SETTINGS_KEY_PRIMARY = "primary_currency"
SETTINGS_KEY_SECONDARY = "secondary_currency"
SETTINGS_KEY_PREFERRED_CURRENCIES = "preferred_currencies"
SETTINGS_KEY_PERIOD_PRESETS = "period_presets"
SETTINGS_KEY_MAX_GROUPS = "max_groups"
SETTINGS_KEY_GROUP_WARNING_PCT = "group_warning_pct"
SETTINGS_KEY_DOLLAR_RATE_PREFERENCE = "dollar_rate_preference"
SETTINGS_KEY_SHORTCUT_CURRENCIES = "shortcut_currencies"
SETTINGS_KEY_TIMEZONE = "timezone"
SETTINGS_KEY_TIMEZONE_MODE = "timezone_mode"
SETTINGS_KEY_LANGUAGE = "language"
SETTINGS_KEY_LANGUAGE_MODE = "language_mode"
SETTINGS_KEY_LIQUIDITY_THRESHOLD_PCT = "liquidity_threshold_pct"
SETTINGS_KEY_SAVINGS_RATE_HEALTHY_PCT = "savings_rate_healthy_pct"
SETTINGS_KEY_SAVINGS_RATE_MODERATE_PCT = "savings_rate_moderate_pct"
SETTINGS_KEY_INCOME_EXPENSE_RATIO_HEALTHY = "income_expense_ratio_healthy"

# Valid values for dollar rate preference.
DOLLAR_RATE_DEFAULT = "mep"

# Valid values for timezone mode (re-exported from the schema for backward-compat with callers).
TIMEZONE_MODE_AUTO = "auto"
TIMEZONE_MODE_MANUAL = "manual"

# Valid values for language mode.
LANGUAGE_MODE_AUTO = "auto"
LANGUAGE_MODE_MANUAL = "manual"

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
    raw_shortcut = settings.get(SETTINGS_KEY_SHORTCUT_CURRENCIES)
    shortcut_currencies = raw_shortcut if isinstance(raw_shortcut, list) else None
    # Fall back to primary + secondary when shortcut currencies are not configured.
    if not shortcut_currencies:
        seen: set[str] = set()
        fallback: list[str] = []
        for c in [primary_currency, secondary_currency]:
            if c and c not in seen:
                seen.add(c)
                fallback.append(c)
        shortcut_currencies = fallback or None
    raw_timezone = settings.get(SETTINGS_KEY_TIMEZONE)
    timezone = raw_timezone if isinstance(raw_timezone, str) and raw_timezone else None
    raw_timezone_mode = settings.get(SETTINGS_KEY_TIMEZONE_MODE)
    timezone_mode = raw_timezone_mode if isinstance(raw_timezone_mode, str) and raw_timezone_mode in TIMEZONE_MODE_VALUES else None
    raw_language = settings.get(SETTINGS_KEY_LANGUAGE)
    language = raw_language if isinstance(raw_language, str) and raw_language in SUPPORTED_LANGUAGES else None
    raw_language_mode = settings.get(SETTINGS_KEY_LANGUAGE_MODE)
    language_mode = raw_language_mode if isinstance(raw_language_mode, str) and raw_language_mode in LANGUAGE_MODE_VALUES else None
    raw_liquidity_threshold = settings.get(SETTINGS_KEY_LIQUIDITY_THRESHOLD_PCT)
    liquidity_threshold_pct = raw_liquidity_threshold if isinstance(raw_liquidity_threshold, int) and 1 <= raw_liquidity_threshold <= 99 else None
    raw_savings_healthy = settings.get(SETTINGS_KEY_SAVINGS_RATE_HEALTHY_PCT)
    savings_rate_healthy_pct = raw_savings_healthy if isinstance(raw_savings_healthy, int) and 1 <= raw_savings_healthy <= 99 else None
    raw_savings_moderate = settings.get(SETTINGS_KEY_SAVINGS_RATE_MODERATE_PCT)
    savings_rate_moderate_pct = raw_savings_moderate if isinstance(raw_savings_moderate, int) and 1 <= raw_savings_moderate <= 99 else None
    raw_ie_ratio = settings.get(SETTINGS_KEY_INCOME_EXPENSE_RATIO_HEALTHY)
    income_expense_ratio_healthy: Decimal | None = None
    if isinstance(raw_ie_ratio, (int, float, str)):
        try:
            candidate = Decimal(str(raw_ie_ratio))
            if Decimal("0.1") <= candidate <= Decimal("10.0"):
                income_expense_ratio_healthy = candidate
        except (ArithmeticError, ValueError):
            income_expense_ratio_healthy = None
    return {
        "primary_currency": primary_currency,
        "secondary_currency": secondary_currency,
        "preferred_currencies": preferred_currencies,
        "period_presets": period_presets,
        "max_groups": max_groups,
        "group_warning_pct": group_warning_pct,
        "dollar_rate_preference": dollar_rate_preference,
        "shortcut_currencies": shortcut_currencies,
        "timezone": timezone,
        "timezone_mode": timezone_mode,
        "language": language,
        "language_mode": language_mode,
        "liquidity_threshold_pct": liquidity_threshold_pct,
        "savings_rate_healthy_pct": savings_rate_healthy_pct,
        "savings_rate_moderate_pct": savings_rate_moderate_pct,
        "income_expense_ratio_healthy": income_expense_ratio_healthy,
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
    shortcut_currencies: list[str] | None = _NOT_SET,
    timezone: str | None = _NOT_SET,
    timezone_mode: str | None = _NOT_SET,
    language: str | None = _NOT_SET,
    language_mode: str | None = _NOT_SET,
    liquidity_threshold_pct: int | None = _NOT_SET,
    savings_rate_healthy_pct: int | None = _NOT_SET,
    savings_rate_moderate_pct: int | None = _NOT_SET,
    income_expense_ratio_healthy: Decimal | None = _NOT_SET,
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
    if shortcut_currencies is not _NOT_SET:
        settings[SETTINGS_KEY_SHORTCUT_CURRENCIES] = shortcut_currencies
    if timezone is not _NOT_SET:
        settings[SETTINGS_KEY_TIMEZONE] = timezone
    if timezone_mode is not _NOT_SET:
        settings[SETTINGS_KEY_TIMEZONE_MODE] = timezone_mode
    if language is not _NOT_SET:
        settings[SETTINGS_KEY_LANGUAGE] = language
    if language_mode is not _NOT_SET:
        settings[SETTINGS_KEY_LANGUAGE_MODE] = language_mode
    if liquidity_threshold_pct is not _NOT_SET:
        settings[SETTINGS_KEY_LIQUIDITY_THRESHOLD_PCT] = liquidity_threshold_pct
    if savings_rate_healthy_pct is not _NOT_SET:
        settings[SETTINGS_KEY_SAVINGS_RATE_HEALTHY_PCT] = savings_rate_healthy_pct
    if savings_rate_moderate_pct is not _NOT_SET:
        settings[SETTINGS_KEY_SAVINGS_RATE_MODERATE_PCT] = savings_rate_moderate_pct
    if income_expense_ratio_healthy is not _NOT_SET:
        # JSONB doesn't natively encode Decimal; store as string so the round-trip survives.
        settings[SETTINGS_KEY_INCOME_EXPENSE_RATIO_HEALTHY] = str(income_expense_ratio_healthy) if income_expense_ratio_healthy is not None else None
    row.settings = settings
    await user_settings_repository.save(session, row)
    await session.commit()
    await session.refresh(row)
    return _settings_to_response(row.settings)
