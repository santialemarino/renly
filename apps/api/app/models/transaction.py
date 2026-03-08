from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.models.investment import Currency


# Kind of transaction (buy, sell, deposit, withdrawal).
class TransactionType(StrEnum):
    buy = "buy"
    sell = "sell"
    deposit = "deposit"
    withdrawal = "withdrawal"


# Single movement (buy/sell/deposit/withdrawal) for an investment.
class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    investment_id: int = Field(foreign_key="investments.id", description="Parent investment.")
    date: date = Field(description="Transaction date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount (positive).")
    currency: Currency = Field(description="Amount currency.")
    type: TransactionType = Field(description="Transaction kind.")
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
