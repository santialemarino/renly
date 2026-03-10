# Request/response schemas for settings endpoints (HTTP contract).

from pydantic import BaseModel, Field

from app.models.investment import Currency


# Response for GET /settings. Current user's display and default currency.
class SettingsResponse(BaseModel):
    display_currencies: list[Currency] = Field(
        description="Currencies shown in the global switch (order preserved).",
    )
    default_currency: Currency | None = Field(
        default=None,
        description="Initial currency on load; null means use first in display_currencies.",
    )


# Body for PUT /settings. Partial update; only provided fields are updated.
class SettingsUpdate(BaseModel):
    display_currencies: list[Currency] | None = Field(
        default=None,
        description="Currencies shown in the global switch (order preserved).",
    )
    default_currency: Currency | None = Field(
        default=None,
        description="Initial currency on load.",
    )
