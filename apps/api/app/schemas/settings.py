# Request/response schemas for settings endpoints (HTTP contract).

from pydantic import BaseModel, Field


# Response for GET /settings. Current user's display currencies and dashboard period presets.
class SettingsResponse(BaseModel):
    primary_currency: str | None = Field(
        default=None,
        description="Primary display currency; shown first in the sidebar switch.",
    )
    secondary_currency: str | None = Field(
        default=None,
        description="Secondary display currency; shown second in the sidebar switch.",
    )
    period_presets: list[str] | None = Field(
        default=None,
        description="Dashboard period presets (e.g. ['1M', '3M', '6M', 'YTD']). Null means use env defaults.",
    )


# Body for PUT /settings. Partial update; only provided fields are updated.
class SettingsUpdate(BaseModel):
    primary_currency: str | None = Field(
        default=None,
        description="Primary display currency.",
    )
    secondary_currency: str | None = Field(
        default=None,
        description="Secondary display currency.",
    )
    period_presets: list[str] | None = Field(
        default=None,
        description="Dashboard period presets (up to 4 codes like '3M', '1Y', 'YTD').",
    )
