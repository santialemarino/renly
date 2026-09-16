# Request/response schemas for account reconciliation endpoints (Bucket 3 #1).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase
from app.schemas.pagination import PaginatedResponse


# Body for POST /accounts/{id}/reconciliations. Records the real balance as of a date; the service
# posts the single adjustment entry that closes the gap.
class AccountReconciliationCreate(RequestBase):
    as_of_date: date_type = Field(description="Date the real balance was read (today or earlier).")
    statement_balance: Decimal = Field(
        description="Real balance the user read off the account. May be negative (overdraft).",
        max_digits=18,
        decimal_places=2,
    )


# One member who would bear part of a SHARED account's difference, and in what proportion.
#
# A PERCENTAGE rather than an amount, and deliberately: the difference is not known until the user types
# a statement balance, and multiplying on the client would drift from what actually gets written — the
# split assigns its rounding remainder to the largest holder so the parts sum to exactly the total. The
# percentage states who is affected without inviting a figure that would not match the row.
class ReconciliationBearerResponse(BaseModel):
    member_id: int = Field(description="Seat that bears part of the difference.")
    display_name: str = Field(description="How that person is shown in the group.")
    percentage: Decimal = Field(description="Their share of the difference, to two decimals; the set sums to 100.", max_digits=5, decimal_places=2)


# Response for GET /accounts/{id}/computed-balance. Backs the reconcile dialog's live difference
# preview: the balance the user is about to true up depends on the date they pick, so the dialog
# re-reads it whenever that date changes rather than assuming today's balance.
class AccountComputedBalanceResponse(BaseModel):
    account_id: int = Field(description="Account id.")
    as_of_date: date_type = Field(description="Date the balance is computed at.")
    balance: Decimal = Field(description="Derived balance at as_of_date, in the account's currency.", max_digits=18, decimal_places=2)
    bearers: list[ReconciliationBearerResponse] = Field(
        default_factory=list,
        description="Who the difference would divide between on a pot's account, largest share first; empty on a private one.",
    )


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
    adjustment_shared_expense_id: int | None = Field(
        default=None, description="Shared adjustment expense id on a pot's account (set when difference < 0)."
    )
    adjustment_shared_income_id: int | None = Field(
        default=None, description="Shared adjustment income id on a pot's account (set when difference > 0)."
    )
    reconciled_by: str | None = Field(
        default=None,
        description="Who ran it, as the pot's group names them. Null on a private account, whose history has one possible author.",
    )
    reconciled_at: datetime = Field(description="When the user ran the reconciliation.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Response for GET /accounts/{id}/reconciliations.
#
# `latest_as_of_date` is carried because only the account's MOST RECENT reconciliation may be deleted,
# and that fact is a property of the whole history rather than of a page: derived from the first row of
# whatever page is on screen, it names page 2's newest row as deletable and the API then refuses it.
# It is the same value delete_reconciliation checks, so the offer and the refusal cannot disagree.
class AccountReconciliationListResponse(PaginatedResponse):
    items: list[AccountReconciliationResponse] = Field(description="Reconciliations on this page, newest first.")
    latest_as_of_date: date_type | None = Field(
        default=None,
        description="as_of_date of the account's newest reconciliation across every page; null when it has never been reconciled.",
    )
