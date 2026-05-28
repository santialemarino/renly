# Request/response schemas for expense endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.expense_entry import ExpenseCategory
from app.schemas.base import RequestBase


# Body for POST /expenses.
class ExpenseCreate(RequestBase):
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Expense amount.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    payment_method: str | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")
    source: str = Field(default="manual", description="Entry origin (manual, shortcut, auto, email_parsed).", max_length=20)
    payment_obligation_id: int | None = Field(
        default=None,
        description="When set, links the expense to an obligation and auto-advances next_due_date (Phase 3, Step E).",
    )
    subscription_id: int | None = Field(
        default=None,
        description=(
            "When set, links the expense to a subscription. Mutually exclusive with payment_obligation_id / installment_id (Phase 3, follow-up 3a)."
        ),
    )
    installment_id: int | None = Field(
        default=None,
        description=(
            "When set, links the expense to an installment plan. Mutually exclusive with "
            "payment_obligation_id / subscription_id (Phase 3, follow-up 3a)."
        ),
    )

    # An expense pays at most one commitment-type. Three nullable FKs (payment_obligation_id /
    # subscription_id / installment_id) coexist on the row, but only one may be set on the
    # same insert. The DB allows arbitrary combinations; this validator is the user-facing
    # guardrail at the request boundary.
    @model_validator(mode="after")
    def validate_commitment_link_exclusivity(self) -> "ExpenseCreate":
        link_count = sum(1 for value in (self.payment_obligation_id, self.subscription_id, self.installment_id) if value is not None)
        if link_count > 1:
            raise ValueError("At most one of payment_obligation_id, subscription_id, installment_id may be set.")
        return self


# Body for PUT /expenses/{id}. Partial update.
class ExpenseUpdate(RequestBase):
    date: date_type | None = Field(default=None, description="Expense date.")
    amount: Decimal | None = Field(default=None, description="Expense amount.", gt=0, max_digits=18, decimal_places=2)
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
    payment_obligation_id: int | None = Field(default=None, description="Linked payment obligation id (Phase 3, Step E).")
    subscription_id: int | None = Field(default=None, description="Linked subscription id (Phase 3, follow-up 3a).")
    installment_id: int | None = Field(default=None, description="Linked installment plan id (Phase 3, follow-up 3a).")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Source plan (subscription or installment) referenced by an auto-charge match.
class AutoChargeMatchSourcePlan(BaseModel):
    id: int = Field(description="Source plan id.")
    name: str = Field(description="Source plan name (for display in the dupe-match confirmation dialog).")


# A single auto-charge match — the existing scheduler-generated expense closest to the candidate.
class AutoChargeMatch(BaseModel):
    expense_id: int = Field(description="Existing expense id.")
    date: date_type = Field(description="Existing expense date.")
    source: str = Field(description="Match source: 'subscription' or 'installment'.")
    source_plan: AutoChargeMatchSourcePlan = Field(description="The subscription / installment that owns the auto-charge.")


# Response for GET /expenses/auto-charge-match. match is null when nothing matches the candidate.
class AutoChargeMatchResponse(BaseModel):
    match: AutoChargeMatch | None = Field(default=None, description="The matching auto-generated expense, or null.")


# Paginated response for GET /expenses.
class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse] = Field(description="Expenses on this page.")
    total: int = Field(description="Total matching expenses.")
    page: int = Field(description="Current page (1-based).")
    page_size: int = Field(description="Items per page.")
    display_currency: str | None = Field(default=None, description="Target currency for converted amounts (None = original).")
