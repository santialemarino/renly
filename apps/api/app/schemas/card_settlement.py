# Request/response schemas for card settlement endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /credit-cards/{id}/settlements.
class CardSettlementCreate(RequestBase):
    date: date_type = Field(description="Settlement date.")
    amount: Decimal = Field(description="Amount paid.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    notes: str | None = Field(default=None, description="Optional notes.")


# Response for a single card settlement.
class CardSettlementResponse(BaseModel):
    id: int = Field(description="Settlement id.")
    credit_card_id: int = Field(description="Card id.")
    date: date_type = Field(description="Settlement date.")
    amount: Decimal = Field(description="Amount paid.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
