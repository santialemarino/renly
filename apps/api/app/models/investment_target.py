from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class InvestmentTarget(SQLModel, table=True):
    __tablename__ = "investment_targets"

    id: int | None = Field(default=None, primary_key=True)
    investment_id: int = Field(foreign_key="investments.id", unique=True)
    target_percentage: Decimal = Field(max_digits=5, decimal_places=2, ge=0, le=100)
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
