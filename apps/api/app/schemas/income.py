# Request/response schemas for income endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.income_entry import IncomeCategory
from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /income.
class IncomeCreate(RequestBase):
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(description="Income amount.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)
    account_id: int | None = Field(default=None, description="Cash/bank account this income was deposited to (optional).")

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)


# Body for PUT /income/{id}. Partial update.
class IncomeUpdate(RequestBase):
    date: date_type | None = Field(default=None, description="Income date.")
    amount: Decimal | None = Field(default=None, description="Income amount.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)
    account_id: int | None = Field(default=None, description="Cash/bank account id. Omit to leave unchanged; send null to clear.")

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)


# Response for a single income entry.
class IncomeResponse(BaseModel):
    id: int = Field(description="Income entry id.")
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(description="Original income amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Amount in the requested display currency.", max_digits=18, decimal_places=2)
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    account_id: int | None = Field(default=None, description="Cash/bank account this income was deposited to.")
    source: str = Field(description="Entry origin (manual, shortcut, auto).")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Paginated response for GET /income.
class IncomeListResponse(BaseModel):
    items: list[IncomeResponse] = Field(description="Income entries on this page.")
    total: int = Field(description="Total matching entries.")
    page: int = Field(description="Current page (1-based).")
    page_size: int = Field(description="Items per page.")
    display_currency: str | None = Field(default=None, description="Target currency for converted amounts (None = original).")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes on this page whose converted_amount is null because no exchange rate was stored.",
    )
