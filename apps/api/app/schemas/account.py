# Request/response schemas for account endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.account import AccountType
from app.schemas.base import RequestBase, validate_supported_currency
from app.schemas.list_scope import ListSectionResponse


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
    scope: str = Field(default="private", description="'private' when the caller owns it, 'shared' when a pot they co-own does.")
    pot_id: int | None = Field(
        default=None,
        description="Pot holding it; null on a private row. Joins the row to its section, which carries the pot's label.",
    )
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Response for GET /accounts. An envelope rather than a bare array, because a grouped list has to say
# what its sections are called and what each one totals — facts about the list, not about any row.
class AccountListResponse(BaseModel):
    items: list[AccountResponse] = Field(description="Every matching account, unpaginated, in scope-major order.")
    sections: list[ListSectionResponse] = Field(
        default_factory=list,
        description="The list's scope sections in row order, each with its per-currency balance total.",
    )
