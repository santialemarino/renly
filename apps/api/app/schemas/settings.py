# Request/response schemas for settings endpoints (HTTP contract).

from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import RequestBase

TIMEZONE_MODE_VALUES = ("auto", "manual")
LANGUAGE_MODE_VALUES = ("auto", "manual")
SUPPORTED_LANGUAGES = ("en", "es")


# Response for GET /settings. User display preferences and app configuration.
class SettingsResponse(BaseModel):
    primary_currency: str | None = Field(
        default=None,
        description="Primary display currency; shown first in the sidebar switch.",
    )
    secondary_currency: str | None = Field(
        default=None,
        description="Secondary display currency; shown second in the sidebar switch.",
    )
    preferred_currencies: list[str] | None = Field(
        default=None,
        description="Preferred currencies shown in their own group in the currency combobox.",
    )
    period_presets: list[str] | None = Field(
        default=None,
        description="Dashboard period presets (e.g. ['1M', '3M', '6M', 'YTD']). Null means use env defaults.",
    )
    max_collections: int | None = Field(
        default=None,
        description="Maximum number of investment collections (soft limit). Null means use env default.",
    )
    collection_warning_pct: int | None = Field(
        default=None,
        description="Percentage of max collections at which the approaching-limit warning appears.",
    )
    dollar_rate_preference: str | None = Field(
        default=None,
        description="Which USD/ARS rate to use: oficial, mep, or blue. Default: mep.",
    )
    shortcut_currencies: list[str] | None = Field(
        default=None,
        description="Currencies shown in the iOS Shortcut currency picker.",
    )
    timezone: str | None = Field(
        default=None,
        description="User's IANA timezone (e.g. America/Argentina/Buenos_Aires). Drives the auto-expense scheduler.",
    )
    timezone_mode: str | None = Field(
        default=None,
        description="Timezone source: 'auto' (browser-detected, kept in sync) or 'manual' (locked).",
    )
    language: str | None = Field(
        default=None,
        description="User's preferred language code (e.g. 'en', 'es'). Drives i18n message loading.",
    )
    language_mode: str | None = Field(
        default=None,
        description="Language source: 'auto' (browser-detected, kept in sync) or 'manual' (locked).",
    )
    liquidity_threshold_pct: int | None = Field(
        default=None,
        description="Liquidity-alert threshold as an integer percent (e.g. 40 = 40%). Null means use env / backend default.",
    )
    savings_rate_healthy_pct: int | None = Field(
        default=None,
        description="Savings rate at or above this percent renders green on the dashboard. Null = backend default (20).",
    )
    savings_rate_moderate_pct: int | None = Field(
        default=None,
        description="Savings rate at or above this percent (but below healthy) renders amber. Null = backend default (10).",
    )
    income_expense_ratio_healthy: Decimal | None = Field(
        default=None,
        description="Income/expense ratio at or above this value renders green. Null = backend default (1.5).",
    )
    onboarding_completed: bool | None = Field(
        default=None,
        description="Whether the user has finished (or dismissed) first-run onboarding. Null when never set (a fresh user).",
    )


# Body for PUT /settings. Partial update; only provided fields are updated.
class SettingsUpdate(RequestBase):
    primary_currency: str | None = Field(
        default=None,
        description="Primary display currency.",
    )
    secondary_currency: str | None = Field(
        default=None,
        description="Secondary display currency.",
    )
    preferred_currencies: list[str] | None = Field(
        default=None,
        description="Preferred currencies for combobox grouping.",
    )
    period_presets: list[str] | None = Field(
        default=None,
        description="Dashboard period presets (up to 4 codes like '3M', '1Y', 'YTD').",
    )
    max_collections: int | None = Field(
        default=None,
        description="Maximum number of investment collections.",
    )
    collection_warning_pct: int | None = Field(
        default=None,
        description="Percentage of max collections for approaching-limit warning.",
    )
    dollar_rate_preference: str | None = Field(
        default=None,
        description="Which USD/ARS rate to use: oficial, mep, or blue.",
    )
    shortcut_currencies: list[str] | None = Field(
        default=None,
        description="Currencies shown in the iOS Shortcut currency picker.",
    )
    timezone: str | None = Field(
        default=None,
        description="User's IANA timezone (e.g. America/Argentina/Buenos_Aires).",
    )
    timezone_mode: str | None = Field(
        default=None,
        description="Timezone source: 'auto' or 'manual'.",
    )
    language: str | None = Field(
        default=None,
        description="User's preferred language code ('en' or 'es').",
    )
    language_mode: str | None = Field(
        default=None,
        description="Language source: 'auto' or 'manual'.",
    )
    liquidity_threshold_pct: int | None = Field(
        default=None,
        description="Liquidity-alert threshold as integer percent. Must be in [1, 99].",
    )
    savings_rate_healthy_pct: int | None = Field(
        default=None,
        description="Savings rate healthy threshold (integer percent in [1, 99]).",
    )
    savings_rate_moderate_pct: int | None = Field(
        default=None,
        description="Savings rate moderate threshold (integer percent in [1, 99]).",
    )
    income_expense_ratio_healthy: Decimal | None = Field(
        default=None,
        description="Income/expense ratio healthy threshold. Must be in [0.1, 10.0].",
    )
    onboarding_completed: bool | None = Field(
        default=None,
        description="Set true when the user finishes or dismisses first-run onboarding.",
    )

    # Rejects timezone values that are not valid IANA zone names.
    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            # ValueError covers a syntactically invalid key (absolute path or '..'); surface the
            # same clean 422 instead of leaking the raw ValueError through Pydantic.
            raise ValueError(f"Unknown IANA timezone: {value!r}.") from exc
        return value

    # Rejects timezone_mode values outside TIMEZONE_MODE_VALUES.
    @field_validator("timezone_mode")
    @classmethod
    def _validate_timezone_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in TIMEZONE_MODE_VALUES:
            raise ValueError(f"timezone_mode must be one of {TIMEZONE_MODE_VALUES}.")
        return value

    # Rejects language values outside SUPPORTED_LANGUAGES.
    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {SUPPORTED_LANGUAGES}.")
        return value

    # Rejects language_mode values outside LANGUAGE_MODE_VALUES.
    @field_validator("language_mode")
    @classmethod
    def _validate_language_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in LANGUAGE_MODE_VALUES:
            raise ValueError(f"language_mode must be one of {LANGUAGE_MODE_VALUES}.")
        return value

    # Rejects liquidity thresholds outside [1, 99].
    @field_validator("liquidity_threshold_pct")
    @classmethod
    def _validate_liquidity_threshold_pct(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not 1 <= value <= 99:
            raise ValueError("liquidity_threshold_pct must be in [1, 99].")
        return value

    # Rejects savings-rate thresholds outside [1, 99].
    @field_validator("savings_rate_healthy_pct", "savings_rate_moderate_pct")
    @classmethod
    def _validate_savings_rate_pct(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not 1 <= value <= 99:
            raise ValueError("savings rate threshold must be in [1, 99].")
        return value

    # Rejects income/expense ratio thresholds outside [0.1, 10.0].
    @field_validator("income_expense_ratio_healthy")
    @classmethod
    def _validate_income_expense_ratio_healthy(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if not Decimal("0.1") <= value <= Decimal("10.0"):
            raise ValueError("income_expense_ratio_healthy must be in [0.1, 10.0].")
        return value
