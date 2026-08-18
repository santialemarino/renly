# Request/response schemas for credit card endpoints.

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /credit-cards.
class CreditCardCreate(RequestBase):
    name: str = Field(description="Card label (e.g. Visa BBVA).", max_length=100)
    closing_day: int = Field(description="Statement closing day (1-31).", ge=1, le=31)
    due_day: int = Field(description="Payment due day (1-31).", ge=1, le=31)
    currency: str = Field(description="Card currency (ISO 4217).", max_length=3)
    monthly_payment: Decimal | None = Field(
        default=None,
        description="Optional typical monthly payment for revolving-debt users. Counts in the liquidity ratio when set.",
        max_digits=18,
        decimal_places=2,
        ge=0,
    )
    default_account_id: int | None = Field(
        default=None,
        description="Optional funding account, in ANY currency. Pre-fills a settlement's 'Paid from'; never creates one.",
    )

    # The card was the last money entity whose currency went unvalidated. Still required now that a
    # funding account need not match it: the validator restricts the card to the supported set AND
    # normalizes case, and an unnormalized "usd" bucket would not match its own settlements' "USD".
    # Same rule the other six request schemas carry.
    _validate_currency = field_validator("currency")(validate_supported_currency)


# Body for PUT /credit-cards/{id}. Partial update.
class CreditCardUpdate(RequestBase):
    name: str | None = Field(default=None, description="Card label.", max_length=100)
    closing_day: int | None = Field(default=None, description="Statement closing day (1-31).", ge=1, le=31)
    due_day: int | None = Field(default=None, description="Payment due day (1-31).", ge=1, le=31)
    currency: str | None = Field(default=None, description="Card currency (ISO 4217).", max_length=3)
    is_active: bool | None = Field(default=None, description="Whether the card is active.")
    monthly_payment: Decimal | None = Field(
        default=None,
        description="Optional typical monthly payment. Send null to clear; counts in the liquidity ratio when set.",
        max_digits=18,
        decimal_places=2,
        ge=0,
    )
    default_account_id: int | None = Field(
        default=None,
        description="Optional funding account, in ANY currency. Send null to clear.",
    )

    _validate_currency = field_validator("currency")(validate_supported_currency)


# Per-currency bucket balance on a credit card (Phase 3 dual-currency model).
class CardBucketBalanceResponse(BaseModel):
    currency: str = Field(description="Bucket currency (ISO 4217).", max_length=3)
    balance: Decimal = Field(description="Balance in this currency (expenses - settlements).", max_digits=18, decimal_places=2)


# Response for a single credit card. Phase 3 dual-currency model: `balances` is
# a per-currency bucket list (always includes the primary currency bucket, plus
# one bucket per other currency with activity). No more cross-currency conversion
# at display time.
class CreditCardResponse(BaseModel):
    id: int = Field(description="Card id.")
    name: str = Field(description="Card label.")
    closing_day: int = Field(description="Statement closing day (1-31).")
    due_day: int = Field(description="Payment due day (1-31).")
    currency: str = Field(description="Primary statement currency (ISO 4217).")
    is_active: bool = Field(description="Whether the card is active.")
    monthly_payment: Decimal | None = Field(
        default=None,
        description="Optional typical monthly payment. When set, counts in the liquidity ratio.",
    )
    default_account_id: int | None = Field(default=None, description="Optional funding account pre-filled on a settlement.")
    balances: list[CardBucketBalanceResponse] = Field(
        default_factory=list,
        description="Per-currency bucket balances. Primary first, then any other currency with activity.",
    )
    has_expenses: bool = Field(description="Whether the card has linked expenses.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
