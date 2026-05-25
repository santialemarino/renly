# Request/response schemas for payment obligation endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.expense_entry import ExpenseCategory
from app.schemas.base import RequestBase


# Body for POST /payment-obligations.
class PaymentObligationCreate(RequestBase):
    name: str = Field(description="Obligation name (e.g. Electricity).", max_length=255)
    amount: Decimal = Field(description="Amount due.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    next_due_date: date_type = Field(description="Anchor date for the next occurrence.")
    recurrence: str | None = Field(
        default=None,
        description="Recurrence pattern (monthly, bimonthly, quarterly, annual). Omit for one-off.",
        max_length=20,
    )
    category: str | None = Field(default=None, description="Free-form obligation label (e.g. ABL, Patente, Cable).", max_length=100)
    expense_category: ExpenseCategory | None = Field(
        default=None,
        description="Structured expense category used to pre-fill Mark Paid and feed finance breakdowns.",
    )
    payment_method: str | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for PUT /payment-obligations/{id}. Partial update.
class PaymentObligationUpdate(RequestBase):
    name: str | None = Field(default=None, description="Obligation name.", max_length=255)
    amount: Decimal | None = Field(default=None, description="Amount due.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    next_due_date: date_type | None = Field(default=None, description="Anchor date for the next occurrence.")
    recurrence: str | None = Field(default=None, description="Recurrence pattern.", max_length=20)
    category: str | None = Field(default=None, description="Free-form obligation label.", max_length=100)
    expense_category: ExpenseCategory | None = Field(default=None, description="Structured expense category.")
    payment_method: str | None = Field(default=None, description="Payment method.", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool | None = Field(default=None, description="Whether the obligation is active.")
    notes: str | None = Field(default=None, description="Optional notes.")


# Response for a single payment obligation.
class PaymentObligationResponse(BaseModel):
    id: int = Field(description="Obligation id.")
    name: str = Field(description="Obligation name.")
    amount: Decimal = Field(description="Original amount due.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Amount in the requested display currency.", max_digits=18, decimal_places=2)
    next_due_date: date_type = Field(description="Anchor date for the next occurrence.")
    recurrence: str | None = Field(default=None, description="Recurrence pattern (None for one-off).")
    category: str | None = Field(default=None, description="Free-form obligation label.")
    expense_category: ExpenseCategory | None = Field(default=None, description="Structured expense category.")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool = Field(description="Whether the obligation is active.")
    notes: str | None = Field(default=None, description="Optional notes.")
    last_payment_date: date_type | None = Field(
        default=None,
        description="Date of the most recent linked expense, or null when never paid (Phase 3, Step E).",
    )
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
