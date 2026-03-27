from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.investment import Currency
from app.models.utils import utcnow


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
    date: date_type = Field(description="Transaction date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount (positive).")
    quantity: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=6, description="Shares/units transacted."
    )
    currency: Currency = Field(description="Amount currency.")
    type: TransactionType = Field(sa_column=Column(SAEnum(TransactionType, name="transaction_type"), nullable=False))
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
