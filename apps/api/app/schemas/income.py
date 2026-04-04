# Request/response schemas for income endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.income_entry import IncomeCategory
from app.schemas.base import RequestBase


# Body for POST /income.
class IncomeCreate(RequestBase):
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(description="Income amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for PUT /income/{id}. Partial update.
class IncomeUpdate(RequestBase):
    date: date_type | None = Field(default=None, description="Income date.")
    amount: Decimal | None = Field(default=None, description="Income amount.", max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.")


# Response for a single income entry.
class IncomeResponse(BaseModel):
    id: int = Field(description="Income entry id.")
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(description="Income amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).")
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.")
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
