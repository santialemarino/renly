from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlmodel import Field, SQLModel, UniqueConstraint


class ExchangeRatePair(StrEnum):
    USD_ARS_OFICIAL = "USD_ARS_OFICIAL"
    USD_ARS_MEP = "USD_ARS_MEP"
    USD_ARS_BLUE = "USD_ARS_BLUE"


class ExchangeRate(SQLModel, table=True):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("date", "pair"),)

    id: int | None = Field(default=None, primary_key=True)
    date: date
    pair: ExchangeRatePair
    rate: Decimal = Field(max_digits=18, decimal_places=6)
    source: str = Field(default="manual", max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
