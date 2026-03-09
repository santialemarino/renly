# Request/response schemas for investment endpoints (HTTP contract).

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.investment import Currency, InvestmentCategory


# Body for POST /investments. Creates a new investment.
class InvestmentCreate(BaseModel):
    name: str = Field(description="Display name of the investment.", max_length=255)
    category: InvestmentCategory = Field(description="Investment type (e.g. cedears, fci).")
    base_currency: Currency = Field(description="Reporting currency (ARS or USD).")
    broker: str | None = Field(default=None, description="Broker or account name.", max_length=100)
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for PUT /investments/{id}. Partial update; only provided fields are updated.
class InvestmentUpdate(BaseModel):
    name: str | None = Field(default=None, description="Display name.", max_length=255)
    category: InvestmentCategory | None = None
    base_currency: Currency | None = None
    broker: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool | None = None


# Response for GET list and GET one, POST and PUT. Exposes investment without user_id.
class InvestmentResponse(BaseModel):
    id: int = Field(description="Investment id.")
    name: str = Field(description="Display name.")
    category: InvestmentCategory = Field(description="Investment type.")
    base_currency: Currency = Field(description="Reporting currency.")
    broker: str | None = Field(default=None, description="Broker or account name.")
    notes: str | None = Field(default=None, description="Optional notes.")
    is_active: bool = Field(description="Whether included in portfolio.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
