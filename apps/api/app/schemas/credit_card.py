# Request/response schemas for credit card endpoints.

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /credit-cards.
class CreditCardCreate(RequestBase):
    name: str = Field(description="Card label (e.g. Visa BBVA).", max_length=100)
    closing_day: int = Field(description="Statement closing day (1-31).", ge=1, le=31)
    due_day: int = Field(description="Payment due day (1-31).", ge=1, le=31)
    currency: str = Field(description="Card currency (ISO 4217).", max_length=3)


# Body for PUT /credit-cards/{id}. Partial update.
class CreditCardUpdate(RequestBase):
    name: str | None = Field(default=None, description="Card label.", max_length=100)
    closing_day: int | None = Field(default=None, description="Statement closing day (1-31).", ge=1, le=31)
    due_day: int | None = Field(default=None, description="Payment due day (1-31).", ge=1, le=31)
    currency: str | None = Field(default=None, description="Card currency (ISO 4217).", max_length=3)
    is_active: bool | None = Field(default=None, description="Whether the card is active.")


# Response for a single credit card.
class CreditCardResponse(BaseModel):
    id: int = Field(description="Card id.")
    name: str = Field(description="Card label.")
    closing_day: int = Field(description="Statement closing day (1-31).")
    due_day: int = Field(description="Payment due day (1-31).")
    currency: str = Field(description="Card currency (ISO 4217).")
    is_active: bool = Field(description="Whether the card is active.")
    balance: Decimal = Field(description="Current card balance (expenses - settlements).", max_digits=18, decimal_places=2)
    has_expenses: bool = Field(description="Whether the card has linked expenses.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
