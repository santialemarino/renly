from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.group_money_settings import SplitMethod
from app.models.income_entry import IncomeCategory
from app.models.utils import utcnow


# Where money a group shares actually ends up (F2).
#   * 'joint' — it lands in a shared account a pot holds, so the pot is worth more and EVERY owner's
#     share rises in proportion. No units are issued and nobody's percentage moves: pro-rata growth
#     needs no ownership event at all, which is the whole point of unit accounting.
#   * 'distributed' — it reaches one person's hands, and becomes each owner's own money in their
#     proportions. Whoever collected it holds the rest as a balance until they pass it on.
# Not derived from the destination account's scope even though it usually could be: it is the choice
# the user made, it is what the remembered per-source default reads back, and it is what lets the API
# refuse a contradiction by name instead of silently reinterpreting one.
class IncomeDestination(StrEnum):
    distributed = "distributed"
    joint = "joint"


# One piece of income a group shares. The mirror of `shared_expenses`, and a sibling table for the
# same reasons: income with one arrival point and an N-way split cannot be one flat `income_entries`
# row, and `income_entries` keeps its simple owner-only RLS while every row here is reachable by each
# member of the group. Each member's own share reaches their normal /income list by a read-time UNION
# over the splits, never a mirrored row.
#
# There is NO receiver column, and for exactly the reason there is no payer column on the expense
# side: money can arrive in a SHARED account, in which case the pot's owners received it in their own
# proportions and no single member is the recipient. Who received what lives on the splits as
# `received_amount`, which one column could not say.
#
# `source_investment_id` drives the F1 default split and nothing else — the group's income from a
# co-owned property divides by that property's pot proportions unless somebody says otherwise. It is
# a pointer, not a dependency: the income really happened, so losing the asset only loses the label.
class SharedIncome(SQLModel, table=True):
    __tablename__ = "shared_income"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group that shares this income.")
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Full amount received, before any split.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217); also the balance bucket this income lands in.")
    category: IncomeCategory | None = Field(
        default=None,
        sa_column=Column(SAEnum(IncomeCategory, name="income_category"), nullable=True),
    )
    split_method: SplitMethod = Field(sa_column=Column(SAEnum(SplitMethod, name="split_method"), nullable=False))
    destination: IncomeDestination = Field(sa_column=Column(SAEnum(IncomeDestination, name="income_destination"), nullable=False))
    source_investment_id: int | None = Field(
        default=None,
        foreign_key="investments.id",
        description="Co-owned asset this income came from; drives the default split. NULL once that asset is gone.",
    )
    paid_to_account_id: int | None = Field(
        default=None, foreign_key="accounts.id", description="Account the money arrived in: one a pot holds, or the recipient's own."
    )
    notes: str | None = Field(default=None, description="Optional notes.")
    created_by: int | None = Field(default=None, foreign_key="users.id", description="Who recorded it; NULL once that account is deleted.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# One member's two sides of one piece of shared income, and the row the income half balances on.
#   * `amount` is what this member is ENTITLED to — their share, the figure that reaches their own
#     /income list and their own income analytics;
#   * `received_amount` is what actually REACHED them.
# Both columns sum to the income's total across its rows, so a member's balance is
# Σ amount − Σ received_amount and the sum over all members is zero in every currency BY
# CONSTRUCTION — the same identity the expense splits carry, with the two sides swapped because an
# entitlement is a claim on the group while cash that has arrived is the group having settled part of
# it.
# When a shared account received the money, the received figures are the pot's ownership proportions
# on the income's date, PINNED here rather than derived, because the ownership ledger is replayed and
# a back-dated event would otherwise silently rewrite a balance two people had already agreed on.
class SharedIncomeSplit(SQLModel, table=True):
    __tablename__ = "shared_income_splits"

    id: int | None = Field(default=None, primary_key=True)
    shared_income_id: int = Field(foreign_key="shared_income.id", description="Income this is one member's position in.")
    group_id: int = Field(foreign_key="groups.id", description="Denormalized from the parent for row-level security.")
    member_id: int = Field(foreign_key="group_members.id", description="The seat this position belongs to.")
    amount: Decimal = Field(default=Decimal(0), max_digits=18, decimal_places=2, description="What this member is entitled to — their share.")
    received_amount: Decimal = Field(default=Decimal(0), max_digits=18, decimal_places=2, description="What actually reached this member.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
