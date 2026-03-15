# Request/response schemas for settings endpoints (HTTP contract).

from pydantic import BaseModel, Field


# Response for GET /settings. Current user's primary and secondary display currency.
class SettingsResponse(BaseModel):
    primary_currency: str | None = Field(
        default=None,
        description="Primary display currency; shown first in the sidebar switch.",
    )
    secondary_currency: str | None = Field(
        default=None,
        description="Secondary display currency; shown second in the sidebar switch.",
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
