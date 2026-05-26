# Request/response schemas for settings endpoints (HTTP contract).

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
    max_groups: int | None = Field(
        default=None,
        description="Maximum number of investment groups (soft limit). Null means use env default.",
    )
    group_warning_pct: int | None = Field(
        default=None,
        description="Percentage of max groups at which the approaching-limit warning appears.",
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
    max_groups: int | None = Field(
        default=None,
        description="Maximum number of investment groups.",
    )
    group_warning_pct: int | None = Field(
        default=None,
        description="Percentage of max groups for approaching-limit warning.",
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

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value!r}.") from exc
        return value

    @field_validator("timezone_mode")
    @classmethod
    def _validate_timezone_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in TIMEZONE_MODE_VALUES:
            raise ValueError(f"timezone_mode must be one of {TIMEZONE_MODE_VALUES}.")
        return value

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {SUPPORTED_LANGUAGES}.")
        return value

    @field_validator("language_mode")
    @classmethod
    def _validate_language_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in LANGUAGE_MODE_VALUES:
            raise ValueError(f"language_mode must be one of {LANGUAGE_MODE_VALUES}.")
        return value

    @field_validator("liquidity_threshold_pct")
    @classmethod
    def _validate_liquidity_threshold_pct(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not 1 <= value <= 99:
            raise ValueError("liquidity_threshold_pct must be in [1, 99].")
        return value
