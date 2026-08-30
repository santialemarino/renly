from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.expense_entry import ExpenseCategory
from app.models.group_money_settings import SplitMethod
from app.models.utils import utcnow


# One expense a group shares. Deliberately NOT a scoped expense_entries row: an expense with one
# funding source and an N-way split cannot be one flat row, and expense_entries keeps its simple
# owner-only RLS while every row here is reachable by each member of the group.
# Each member's own share reaches their normal /expenses list by a read-time UNION over the splits —
# never a mirrored expense_entries row, because an edit here would then have to chase every copy.
#
# There is NO payer column, and that is not a style choice: money can come from a SHARED account, in
# which case the pot's owners fronted it in their own proportions and no single member is the payer.
# Who fronted what lives on the splits as `paid_amount`, which one column could not say.
#
# The funding source is at most one of the two — an account draws cash on the spot, a card raises a
# liability now and draws cash later at settlement — and naming NEITHER is legal and common: an
# expense somebody paid outside Renly still splits.
class SharedExpense(SQLModel, table=True):
    __tablename__ = "shared_expenses"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group that shares this expense.")
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Full amount of the expense, before any split.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217); also the balance bucket this expense lands in.")
    category: ExpenseCategory | None = Field(
        default=None,
        sa_column=Column(SAEnum(ExpenseCategory, name="expense_category"), nullable=True),
    )
    split_method: SplitMethod = Field(sa_column=Column(SAEnum(SplitMethod, name="split_method"), nullable=False))
    paid_from_account_id: int | None = Field(
        default=None, foreign_key="accounts.id", description="Account the money left; may be a member's own or one a pot holds."
    )
    payment_method: str | None = Field(default=None, max_length=20, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(default=None, foreign_key="credit_cards.id", description="Card charged (when payment_method = credit_card).")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_by: int | None = Field(default=None, foreign_key="users.id", description="Who recorded it; NULL once that account is deleted.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# One member's two sides of one shared expense, and the row the whole feature balances on.
#   * `amount` is what this member CONSUMED — their share, the figure that reaches their own /expenses
#     list and their own spending analytics;
#   * `paid_amount` is what this member FRONTED.
# Both columns sum to the expense's total across its rows, so a member's balance is
# Σ paid_amount − Σ amount and the sum over all members is zero in every currency BY CONSTRUCTION.
# That single identity is what makes every case in the spec's §4.2 table one implementation, the
# money-fronted-by-a-shared-account one included: the pot's owners front it in their ownership
# proportions at that date, PINNED here rather than derived, because the ownership ledger is replayed
# and a back-dated event would otherwise silently rewrite an old balance.
class SharedExpenseSplit(SQLModel, table=True):
    __tablename__ = "shared_expense_splits"

    id: int | None = Field(default=None, primary_key=True)
    shared_expense_id: int = Field(foreign_key="shared_expenses.id", description="Expense this is one member's position in.")
    group_id: int = Field(foreign_key="groups.id", description="Denormalized from the parent for row-level security.")
    member_id: int = Field(foreign_key="group_members.id", description="The seat this position belongs to.")
    amount: Decimal = Field(default=Decimal(0), max_digits=18, decimal_places=2, description="What this member consumed — their share.")
    paid_amount: Decimal = Field(default=Decimal(0), max_digits=18, decimal_places=2, description="What this member fronted.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
