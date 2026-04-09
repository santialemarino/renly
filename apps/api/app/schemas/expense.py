# Request/response schemas for expense endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.expense_entry import ExpenseCategory
from app.schemas.base import RequestBase


# Body for POST /expenses.
class ExpenseCreate(RequestBase):
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Expense amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    payment_method: str | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")
    source: str = Field(default="manual", description="Entry origin (manual, shortcut, auto, email_parsed).", max_length=20)


# Body for PUT /expenses/{id}. Partial update.
class ExpenseUpdate(RequestBase):
    date: date_type | None = Field(default=None, description="Expense date.")
    amount: Decimal | None = Field(default=None, description="Expense amount.", max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    payment_method: str | None = Field(default=None, description="Payment method.", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id.")


# Response for a single expense entry.
class ExpenseResponse(BaseModel):
    id: int = Field(description="Expense id.")
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Original expense amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Amount in the requested display currency.", max_digits=18, decimal_places=2)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    source: str = Field(description="Entry origin (manual, shortcut, auto, email_parsed).")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Paginated response for GET /expenses.
class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse] = Field(description="Expenses on this page.")
    total: int = Field(description="Total matching expenses.")
    page: int = Field(description="Current page (1-based).")
    page_size: int = Field(description="Items per page.")
    display_currency: str | None = Field(default=None, description="Target currency for converted amounts (None = original).")
