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
#
# A POT's account carries the same pair one table over: adjustment_shared_expense_id /
# adjustment_shared_income_id, because a private entry cannot be the adjustment there. expense_entries
# and income_entries keep user_id NOT NULL and carry no pot_id (§3 — a shared flow lives in its own
# table), and the pot account's balance sums filter on that same user_id — so such a row would leave
# the drift open. What refuses it is `ensure_private_funding` in the service rather than any constraint
# here, which is why that guard is load-bearing rather than decorative.
# The shared row is split across the pot's owners in their ownership proportions on BOTH sides at once,
# so it nets to zero between them: the drift is the pot's own money, and correcting it creates no debt
# between the people who hold it.
# The two pairs are mutually exclusive per scope, enforced by CHECK constraints rather than by this
# service, so a row read back says which kind of adjustment to look for from its scope alone.
class AccountReconciliation(SQLModel, table=True):
    __tablename__ = "account_reconciliations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(
        default=None, foreign_key="users.id", description="Owner, denormalized from the parent for row-level security; NULL when a pot owns it."
    )
    pot_id: int | None = Field(default=None, foreign_key="pots.id", description="Pot that co-owns the parent; NULL when it is private.")
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
    adjustment_shared_expense_id: int | None = Field(
        default=None,
        foreign_key="shared_expenses.id",
        description="Back-pointer to the shared adjustment expense on a POT's account (set when difference < 0).",
    )
    adjustment_shared_income_id: int | None = Field(
        default=None,
        foreign_key="shared_income.id",
        description="Back-pointer to the shared adjustment income on a POT's account (set when difference > 0).",
    )
    created_by: int | None = Field(default=None, foreign_key="users.id", description="Who ran it; NULL once that account is deleted.")
    reconciled_at: datetime = Field(default_factory=utcnow, description="When the user ran the reconciliation.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
