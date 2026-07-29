from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Point-in-time true-up of a cash/bank account against its real balance (Bucket 3 #1 — Option F).
# The cash/bank sibling of CardReconciliation, deliberately simpler: an account is single-currency and
# its balance is a point-in-time figure, so there is no statement period, no currency bucket, and no
# is_stale flag — re-reconciling just appends a newer row, which supersedes the earlier one by date.
# computed_balance is the account's derived balance at as_of_date at the time of reconciliation.
# difference = statement_balance - computed_balance. A positive difference (the account really holds
# more than Renly knew) creates an adjustment income; a negative one creates an adjustment expense;
# zero creates nothing.
# adjustment_expense_id / adjustment_income_id back-reference the adjustment row; the corresponding
# expense_entries.account_reconciliation_id / income_entries.account_reconciliation_id close the loop
# with ON DELETE CASCADE, so deleting a reconciliation always removes the adjustment it created.
class AccountReconciliation(SQLModel, table=True):
    __tablename__ = "account_reconciliations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    account_id: int = Field(foreign_key="accounts.id", description="Account being reconciled.")
    as_of_date: date_type = Field(description="Date the real balance was read.")
    statement_balance: Decimal = Field(max_digits=18, decimal_places=2, description="Real balance the user read off the account.")
    computed_balance: Decimal = Field(max_digits=18, decimal_places=2, description="Derived balance at as_of_date when reconciled.")
    difference: Decimal = Field(max_digits=18, decimal_places=2, description="statement_balance - computed_balance.")
    adjustment_expense_id: int | None = Field(
        default=None,
        foreign_key="expense_entries.id",
        description="Back-pointer to the adjustment expense (set when difference < 0).",
    )
    adjustment_income_id: int | None = Field(
        default=None,
        foreign_key="income_entries.id",
        description="Back-pointer to the adjustment income (set when difference > 0).",
    )
    reconciled_at: datetime = Field(default_factory=utcnow, description="When the user ran the reconciliation.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
