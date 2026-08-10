# Request/response schemas for subscription endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.payment_method import PaymentMethod, ensure_account_pairing, ensure_payment_pairing
from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /subscriptions.
class SubscriptionCreate(RequestBase):
    name: str = Field(description="Subscription name (e.g. Netflix).", max_length=255)
    amount: Decimal = Field(description="Charge amount per billing cycle.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    billing_cycle: str = Field(description="Billing cycle (monthly, annual, quarterly, biweekly, weekly).", max_length=20)
    next_billing_date: date_type = Field(description="Date of next billing event.")
    payment_method: PaymentMethod | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")
    default_account_id: int | None = Field(
        default=None,
        description="Optional account, in the subscription's currency, that each emitted charge is linked to (non-card methods only).",
    )

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)

    # credit_card_id only pairs with the credit_card method. The reverse is NOT required —
    # a card-less credit_card entry is allowed (zero-card users, imports). A default funding
    # account is the mirror rule: a card-paid plan draws cash at the card settlement, never here.
    @model_validator(mode="after")
    def validate_payment_pairing(self) -> "SubscriptionCreate":
        ensure_payment_pairing(self.payment_method, self.credit_card_id)
        ensure_account_pairing(self.payment_method, self.default_account_id)
        return self


# Body for PUT /subscriptions/{id}. Partial update.
class SubscriptionUpdate(RequestBase):
    name: str | None = Field(default=None, description="Subscription name.", max_length=255)
    amount: Decimal | None = Field(default=None, description="Charge amount per billing cycle.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    billing_cycle: str | None = Field(default=None, description="Billing cycle.", max_length=20)
    payment_method: PaymentMethod | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    default_account_id: int | None = Field(
        default=None,
        description="Optional account each emitted charge is linked to. Send null to clear.",
    )
    is_active: bool | None = Field(default=None, description="Whether the subscription is active.")
    next_billing_date: date_type | None = Field(default=None, description="Date of next billing event.")

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)

    # Same-request pairing guards: each only fires when BOTH its keys were provided. The merged
    # effective checks (request fields over the stored row) live in the service.
    @model_validator(mode="after")
    def validate_payment_pairing(self) -> "SubscriptionUpdate":
        provided = self.model_fields_set
        if "payment_method" in provided and "credit_card_id" in provided:
            ensure_payment_pairing(self.payment_method, self.credit_card_id)
        if "payment_method" in provided and "default_account_id" in provided:
            ensure_account_pairing(self.payment_method, self.default_account_id)
        return self


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
    default_account_id: int | None = Field(default=None, description="Optional account each emitted charge is linked to.")
    is_active: bool = Field(description="Whether the subscription is active.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
