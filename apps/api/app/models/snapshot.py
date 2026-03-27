from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models.investment import Currency
from app.models.utils import utcnow


# Point-in-time value of an investment (one per investment per date).
class InvestmentSnapshot(SQLModel, table=True):
    __tablename__ = "investment_snapshots"
    __table_args__ = (UniqueConstraint("investment_id", "date"),)

    id: int | None = Field(default=None, primary_key=True)
    investment_id: int = Field(foreign_key="investments.id", description="Parent investment.")
    date: date_type = Field(description="Snapshot date.")
    value: Decimal = Field(max_digits=18, decimal_places=2, description="Value on this date.")
    quantity: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=6, description="Shares/units (for ticker-linked investments)."
    )
    currency: Currency = Field(description="Value currency.")
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
