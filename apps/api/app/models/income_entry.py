from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Income category (salary, freelance, investment_returns, etc.).
class IncomeCategory(StrEnum):
    account_adjustment = "account_adjustment"
    bonus = "bonus"
    card_credits_and_refunds = "card_credits_and_refunds"
    dividends = "dividends"
    freelance = "freelance"
    gifts = "gifts"
    investment_returns = "investment_returns"
    other = "other"
    refunds = "refunds"
    rental_income = "rental_income"
    salary = "salary"
    sales = "sales"


# User income entry (daily income tracking).
class IncomeEntry(SQLModel, table=True):
    __tablename__ = "income_entries"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Income amount.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217).")
    category: IncomeCategory | None = Field(
        default=None,
        sa_column=Column(SAEnum(IncomeCategory, name="income_category"), nullable=True),
    )
    notes: str | None = Field(default=None, description="Optional notes.")
    source: str = Field(default="manual", max_length=20, description="Entry origin (manual, shortcut, auto, reconciliation).")
    reconciliation_id: int | None = Field(
        default=None,
        foreign_key="card_reconciliations.id",
        description="Owning card reconciliation when this row is the adjustment income from the card reconciliation flow.",
    )
    account_reconciliation_id: int | None = Field(
        default=None,
        foreign_key="account_reconciliations.id",
        description="Owning account reconciliation when this row is the adjustment income from the account reconciliation flow.",
    )
    account_id: int | None = Field(default=None, foreign_key="accounts.id", description="Cash/bank account this income was deposited to (optional).")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
