# Request/response schemas for card settlement endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /credit-cards/{id}/settlements.
class CardSettlementCreate(RequestBase):
    date: date_type = Field(description="Settlement date.")
    amount: Decimal = Field(description="Amount paid.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    account_id: int | None = Field(default=None, description="Cash/bank account the payment was drawn from (optional).")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    # Normalizes case as well as validating, so a settlement's currency compares to the funding
    # account's without a case-insensitive fallback.
    _validate_currency = field_validator("currency")(validate_supported_currency)


# Response for a single card settlement. account_name is denormalized from the account so a client can
# render which account paid the bill without a second lookup — and so an ARCHIVED account still reads by
# name, which a client-side join against its own active-accounts list could not do. Null exactly when
# account_id is null (an unlinked settlement: the card debt dropped, no cash was recorded leaving).
class CardSettlementResponse(BaseModel):
    id: int = Field(description="Settlement id.")
    credit_card_id: int = Field(description="Card id.")
    date: date_type = Field(description="Settlement date.")
    amount: Decimal = Field(description="Amount paid.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).")
    account_id: int | None = Field(default=None, description="Cash/bank account the payment was drawn from.")
    account_name: str | None = Field(default=None, description="Name of that account, for display.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
