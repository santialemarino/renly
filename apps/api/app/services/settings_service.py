from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.currency import DOLLAR_RATE_DEFAULT
from app.models.user import User
from app.models.user_settings import UserSettings
from app.repositories import user_settings_repository
from app.schemas.settings import LANGUAGE_MODE_VALUES, SUPPORTED_LANGUAGES, TIMEZONE_MODE_VALUES
from app.utils.dates import today_in_timezone
from app.utils.liquidity import DEFAULT_LIQUIDITY_THRESHOLD_PCT

SETTINGS_KEY_PRIMARY = "primary_currency"
SETTINGS_KEY_SECONDARY = "secondary_currency"
SETTINGS_KEY_PREFERRED_CURRENCIES = "preferred_currencies"
SETTINGS_KEY_PERIOD_PRESETS = "period_presets"
SETTINGS_KEY_MAX_COLLECTIONS = "max_collections"
SETTINGS_KEY_COLLECTION_WARNING_PCT = "collection_warning_pct"
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
SETTINGS_KEY_ONBOARDING_COMPLETED = "onboarding_completed"
SETTINGS_KEY_SAMPLES_RETIRED_INVESTMENTS = "samples_retired_investments"
SETTINGS_KEY_SAMPLES_RETIRED_EXPENSES = "samples_retired_expenses"
SETTINGS_KEY_SAMPLES_RETIRED_INCOME = "samples_retired_income"
SETTINGS_KEY_TOUR_COMPLETED = "tour_completed"

# Per-entity "first-run sample retired" flags. Each is latched (server-side) when the user first
# creates that entity or clears that section's sample, so the section's sample shows only until the
# user has done it once. Keyed by the entity name used across the onboarding surface.
SAMPLE_RETIRED_KEYS = {
    "investments": SETTINGS_KEY_SAMPLES_RETIRED_INVESTMENTS,
    "expenses": SETTINGS_KEY_SAMPLES_RETIRED_EXPENSES,
    "income": SETTINGS_KEY_SAMPLES_RETIRED_INCOME,
}

# Default UI language; also the fallback locale for transactional emails when none is stored.
DEFAULT_LANGUAGE = SUPPORTED_LANGUAGES[0]

_NOT_SET = object()


# Normalizes the raw settings blob into the response dict: type-checks every key and applies fallbacks.
def _settings_to_response(settings: dict) -> dict:
    raw_primary = settings.get(SETTINGS_KEY_PRIMARY)
    primary_currency = raw_primary if isinstance(raw_primary, str) and raw_primary else None
    raw_secondary = settings.get(SETTINGS_KEY_SECONDARY)
    secondary_currency = raw_secondary if isinstance(raw_secondary, str) and raw_secondary else None
    raw_preferred = settings.get(SETTINGS_KEY_PREFERRED_CURRENCIES)
    preferred_currencies = raw_preferred if isinstance(raw_preferred, list) else None
    raw_presets = settings.get(SETTINGS_KEY_PERIOD_PRESETS)
    period_presets = raw_presets if isinstance(raw_presets, list) else None
    raw_max_collections = settings.get(SETTINGS_KEY_MAX_COLLECTIONS)
    max_collections = raw_max_collections if isinstance(raw_max_collections, int) else None
    raw_warning_pct = settings.get(SETTINGS_KEY_COLLECTION_WARNING_PCT)
    collection_warning_pct = raw_warning_pct if isinstance(raw_warning_pct, int) else None
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
    raw_onboarding = settings.get(SETTINGS_KEY_ONBOARDING_COMPLETED)
    onboarding_completed = raw_onboarding if isinstance(raw_onboarding, bool) else None
    # Onboarding-internal, not exposed on SettingsResponse — read by onboarding_service to gate the
    # per-section first-run samples. A missing/malformed key reads as False (sample still eligible).
    samples_retired = {entity: settings.get(key) is True for entity, key in SAMPLE_RETIRED_KEYS.items()}
    # Onboarding-internal too — gates the first-run welcome tour. A missing key reads as False.
    tour_completed = settings.get(SETTINGS_KEY_TOUR_COMPLETED) is True
    return {
        "primary_currency": primary_currency,
        "secondary_currency": secondary_currency,
        "preferred_currencies": preferred_currencies,
        "period_presets": period_presets,
        "max_collections": max_collections,
        "collection_warning_pct": collection_warning_pct,
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
        "onboarding_completed": onboarding_completed,
        "samples_retired": samples_retired,
        "tour_completed": tour_completed,
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
    max_collections: int | None = _NOT_SET,
    collection_warning_pct: int | None = _NOT_SET,
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
    onboarding_completed: bool | None = _NOT_SET,
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
    if max_collections is not _NOT_SET:
        settings[SETTINGS_KEY_MAX_COLLECTIONS] = max_collections
    if collection_warning_pct is not _NOT_SET:
        settings[SETTINGS_KEY_COLLECTION_WARNING_PCT] = collection_warning_pct
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
    if onboarding_completed is not _NOT_SET:
        settings[SETTINGS_KEY_ONBOARDING_COMPLETED] = onboarding_completed
    row.settings = settings
    await user_settings_repository.save(session, row)
    await session.commit()
    await session.refresh(row)
    return _settings_to_response(row.settings)


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


# Reads the user's IANA timezone from settings. Returns None when unset (callers fall back to UTC).
async def get_user_timezone(session: AsyncSession, user_id: int) -> str | None:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    if row and row.settings:
        tz = row.settings.get(SETTINGS_KEY_TIMEZONE)
        if isinstance(tz, str) and tz:
            return tz
    return None


# Coerces a raw settings value into a supported language, or DEFAULT_LANGUAGE when unset/invalid.
def _language_or_default(value: object) -> str:
    return value if isinstance(value, str) and value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


# Reads the user's stored UI language for localizing transactional emails. Returns DEFAULT_LANGUAGE
# when unset or invalid, so a caller always has a valid locale to hand the email templates.
async def get_user_language(session: AsyncSession, user_id: int) -> str:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    return _language_or_default(row.settings.get(SETTINGS_KEY_LANGUAGE) if row and row.settings else None)


# Batch variant of get_user_language: returns {user_id: language} for every requested id (defaulting
# ids with no stored/valid language), in one query. Used to localize admin feedback notifications
# without an N+1 over the admin list.
async def get_languages_by_user_ids(session: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    stored = await user_settings_repository.get_languages_by_user_ids(session, user_ids)
    return {user_id: _language_or_default(stored.get(user_id)) for user_id in user_ids}


# Seeds a brand-new user's stored language (called from register before the shared commit, so it
# joins that transaction — does NOT commit here). Gives later transactional emails to the user a
# stored preference to localize by. The user has no settings row yet, so this creates it.
async def seed_language(session: AsyncSession, user_id: int, language: str) -> None:
    await user_settings_repository.create(session, UserSettings(user_id=user_id, settings={SETTINGS_KEY_LANGUAGE: language}))


# Resolves the user's local calendar "today" from an already-loaded IANA timezone (no DB read) —
# the pure counterpart of get_user_today for callers that already hold the timezone. `now_utc` is
# injectable for tests.
def today_for_timezone(timezone: str | None, now_utc: datetime | None = None) -> date_type:
    return today_in_timezone(now_utc or datetime.now(UTC), timezone)


# Returns the user's local calendar date "today" (settings timezone, UTC fallback) — the
# request-path counterpart of the scheduler's per-user local-date derivation. `now_utc` is
# injectable for tests, mirroring auto_expense_service.
async def get_user_today(session: AsyncSession, user_id: int, now_utc: datetime | None = None) -> date_type:
    tz = await get_user_timezone(session, user_id)
    return today_for_timezone(tz, now_utc)


# The per-request settings the dashboard aggregates need together.
class RequestSettings(NamedTuple):
    dollar_preference: str
    timezone: str | None
    liquidity_threshold_pct: int


# Loads dollar-rate preference, IANA timezone, and the liquidity threshold from ONE user_settings
# read for a request that needs several of them, instead of the separate indexed reads the
# individual getters (get_dollar_pref + get_user_timezone + get_liquidity_threshold) would each do.
# Same parsing and fallbacks as those getters — no behaviour change, just one round-trip (P09 D4).
async def get_request_settings(session: AsyncSession, user_id: int) -> RequestSettings:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    data = row.settings if row and row.settings else {}
    raw_pref = data.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
    dollar_preference = raw_pref if isinstance(raw_pref, str) and raw_pref else DOLLAR_RATE_DEFAULT
    raw_tz = data.get(SETTINGS_KEY_TIMEZONE)
    timezone = raw_tz if isinstance(raw_tz, str) and raw_tz else None
    raw_threshold = data.get(SETTINGS_KEY_LIQUIDITY_THRESHOLD_PCT)
    liquidity_threshold_pct = raw_threshold if isinstance(raw_threshold, int) and 1 <= raw_threshold <= 99 else DEFAULT_LIQUIDITY_THRESHOLD_PCT
    return RequestSettings(dollar_preference, timezone, liquidity_threshold_pct)


# Retires a section's first-run sample by latching its per-entity flag (alongside the entity being
# created, or on dismiss). Idempotent; does NOT commit. `entity` must be a key of SAMPLE_RETIRED_KEYS.
async def retire_sample(session: AsyncSession, user_id: int, entity: str) -> None:
    await user_settings_repository.latch_flag(session, user_id, SAMPLE_RETIRED_KEYS[entity])


# Latches the first-run welcome tour as completed so it never auto-shows again. Idempotent; does NOT commit.
async def complete_tour(session: AsyncSession, user_id: int) -> None:
    await user_settings_repository.latch_flag(session, user_id, SETTINGS_KEY_TOUR_COMPLETED)
