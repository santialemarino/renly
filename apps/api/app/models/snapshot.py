from datetime import date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models.investment import Currency


class InvestmentSnapshot(SQLModel, table=True):
    __tablename__ = "investment_snapshots"
    __table_args__ = (UniqueConstraint("investment_id", "date"),)

    id: int | None = Field(default=None, primary_key=True)
    investment_id: int = Field(foreign_key="investments.id")
    date: date
    value: Decimal = Field(max_digits=18, decimal_places=2)
    currency: Currency
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
