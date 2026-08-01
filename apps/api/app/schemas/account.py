# Request/response schemas for account endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.account import AccountType
from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /accounts.
class AccountCreate(RequestBase):
    name: str = Field(description="Account label (e.g. Caja de ahorro $).", max_length=255)
    type: AccountType = Field(description="Account type (cash, bank, wallet, other).")
    currency: str = Field(description="Account currency (ISO 4217).", max_length=3)
    opening_balance: Decimal = Field(default=Decimal(0), description="Balance at opening_date.", max_digits=18, decimal_places=2)
    opening_date: date_type = Field(description="Date the opening_balance is measured at.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    _validate_currency = field_validator("currency")(validate_supported_currency)


# Body for PUT /accounts/{id}. Partial update; only provided fields are updated.
class AccountUpdate(RequestBase):
    name: str | None = Field(default=None, description="Account label.", max_length=255)
    type: AccountType | None = Field(default=None, description="Account type (cash, bank, wallet, other).")
    currency: str | None = Field(default=None, description="Account currency (ISO 4217).", max_length=3)
    opening_balance: Decimal | None = Field(default=None, description="Balance at opening_date.", max_digits=18, decimal_places=2)
    opening_date: date_type | None = Field(default=None, description="Date the opening_balance is measured at.")
    is_active: bool | None = Field(default=None, description="Whether the account is active.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    _validate_currency = field_validator("currency")(validate_supported_currency)


# Response for GET list and GET one, POST and PUT. `balance` is derived at query time
# (opening_balance + linked income − linked expenses − settlements paid from it), in the account's own currency.
class AccountResponse(BaseModel):
    id: int = Field(description="Account id.")
    name: str = Field(description="Account label.")
    type: AccountType = Field(description="Account type.")
    currency: str = Field(description="Account currency (ISO 4217).")
    opening_balance: Decimal = Field(description="Balance at opening_date.")
    opening_date: date_type = Field(description="Date the opening_balance is measured at.")
    balance: Decimal = Field(description="Current derived balance in the account's currency.")
    is_active: bool = Field(description="Whether the account is active.")
    notes: str | None = Field(default=None, description="Optional notes.")
    has_links: bool = Field(default=False, description="Whether any expense/income/settlement/transfer links this account (locks its currency).")
    last_reconciled_date: date_type | None = Field(default=None, description="as_of_date of the most recent reconciliation, if any.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
