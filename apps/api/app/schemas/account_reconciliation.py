# Request/response schemas for account reconciliation endpoints (Bucket 3 #1).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /accounts/{id}/reconciliations. Records the real balance as of a date; the service
# posts the single adjustment entry that closes the gap.
class AccountReconciliationCreate(RequestBase):
    as_of_date: date_type = Field(description="Date the real balance was read (today or earlier).")
    statement_balance: Decimal = Field(
        description="Real balance the user read off the account. May be negative (overdraft).",
        max_digits=18,
        decimal_places=2,
    )


# Response for GET /accounts/{id}/computed-balance. Backs the reconcile dialog's live difference
# preview: the balance the user is about to true up depends on the date they pick, so the dialog
# re-reads it whenever that date changes rather than assuming today's balance.
class AccountComputedBalanceResponse(BaseModel):
    account_id: int = Field(description="Account id.")
    as_of_date: date_type = Field(description="Date the balance is computed at.")
    balance: Decimal = Field(description="Derived balance at as_of_date, in the account's currency.", max_digits=18, decimal_places=2)


# Response for a single reconciliation. Returned by GET list and POST.
class AccountReconciliationResponse(BaseModel):
    id: int = Field(description="Reconciliation id.")
    account_id: int = Field(description="Account id.")
    as_of_date: date_type = Field(description="Date the real balance was read.")
    statement_balance: Decimal = Field(description="Real balance the user read off the account.", max_digits=18, decimal_places=2)
    computed_balance: Decimal = Field(description="Derived balance at as_of_date at reconciliation time.", max_digits=18, decimal_places=2)
    difference: Decimal = Field(description="statement_balance - computed_balance.", max_digits=18, decimal_places=2)
    adjustment_expense_id: int | None = Field(default=None, description="Adjustment expense id (set when difference < 0).")
    adjustment_income_id: int | None = Field(default=None, description="Adjustment income id (set when difference > 0).")
    reconciled_at: datetime = Field(description="When the user ran the reconciliation.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
