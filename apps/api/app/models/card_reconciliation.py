from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Per-bucket statement true-up against the bank (Phase 3, Step 5 — Option F).
# One row per (card_id, currency, period_start, period_end) — uniqueness enforced at the DB.
# computed_balance is the bucket's running balance at period_end at the time of reconciliation.
# difference = statement_balance - computed_balance. Both non-zero directions create ONE signed,
# card-linked adjustment EXPENSE — positive for a fee/tax, negative for a credit — because a bucket
# balance is `sum(expenses) - sum(settlements)` and an income row could never move it. Zero creates
# nothing. adjustment_income_id is retained for the historical shape but is no longer written.
# adjustment_expense_id back-references the adjustment row; expense_entries.reconciliation_id closes
# the loop with ON DELETE CASCADE.
# is_stale flips to true when an expense or settlement inside the period is created / updated / deleted
# after this reconciliation was written. Re-reconciling replaces (delete + cascade + insert).
class CardReconciliation(SQLModel, table=True):
    __tablename__ = "card_reconciliations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    card_id: int = Field(foreign_key="credit_cards.id", description="Card being reconciled.")
    currency: str = Field(max_length=3, description="Bucket currency (ISO 4217).")
    period_start: date_type = Field(description="Inclusive first day of the statement period.")
    period_end: date_type = Field(description="Inclusive last day of the statement period (the closing date).")
    statement_balance: Decimal = Field(max_digits=18, decimal_places=2, description="Bank's actual statement balance.")
    computed_balance: Decimal = Field(max_digits=18, decimal_places=2, description="Running balance at period_end when reconciled.")
    difference: Decimal = Field(max_digits=18, decimal_places=2, description="statement_balance - computed_balance.")
    adjustment_expense_id: int | None = Field(
        default=None,
        foreign_key="expense_entries.id",
        description="Back-pointer to the adjustment expense (set when difference > 0).",
    )
    adjustment_income_id: int | None = Field(
        default=None,
        foreign_key="income_entries.id",
        description="Legacy back-pointer to an adjustment income; no longer written (credits are signed expenses).",
    )
    is_stale: bool = Field(default=False, description="True when a relevant edit inside the period happened after reconciliation.")
    reconciled_at: datetime = Field(default_factory=utcnow, description="When the user ran the reconciliation.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
