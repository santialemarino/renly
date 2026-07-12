# Request/response schemas for subscription endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /subscriptions.
class SubscriptionCreate(RequestBase):
    name: str = Field(description="Subscription name (e.g. Netflix).", max_length=255)
    amount: Decimal = Field(description="Charge amount per billing cycle.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    billing_cycle: str = Field(description="Billing cycle (monthly, annual, quarterly, biweekly, weekly).", max_length=20)
    next_billing_date: date_type = Field(description="Date of next billing event.")
    payment_method: str | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)


# Body for PUT /subscriptions/{id}. Partial update.
class SubscriptionUpdate(RequestBase):
    name: str | None = Field(default=None, description="Subscription name.", max_length=255)
    amount: Decimal | None = Field(default=None, description="Charge amount per billing cycle.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    billing_cycle: str | None = Field(default=None, description="Billing cycle.", max_length=20)
    payment_method: str | None = Field(default=None, description="Payment method.", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool | None = Field(default=None, description="Whether the subscription is active.")
    next_billing_date: date_type | None = Field(default=None, description="Date of next billing event.")

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)


# Response for a single subscription.
class SubscriptionResponse(BaseModel):
    id: int = Field(description="Subscription id.")
    name: str = Field(description="Subscription name.")
    amount: Decimal = Field(description="Original charge amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Amount in the requested display currency.", max_digits=18, decimal_places=2)
    billing_cycle: str = Field(description="Billing cycle (monthly, annual, quarterly, biweekly, weekly).")
    next_billing_date: date_type = Field(description="Date of next billing event.")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool = Field(description="Whether the subscription is active.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
