from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlmodel import Field, SQLModel, UniqueConstraint


# Exchange rate pair (e.g. USD/ARS official, MEP, blue).
class ExchangeRatePair(StrEnum):
    USD_ARS_OFICIAL = "USD_ARS_OFICIAL"
    USD_ARS_MEP = "USD_ARS_MEP"
    USD_ARS_BLUE = "USD_ARS_BLUE"


# Daily exchange rate for a pair (one row per date per pair).
class ExchangeRate(SQLModel, table=True):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("date", "pair"),)

    id: int | None = Field(default=None, primary_key=True)
    date: date = Field(description="Rate date.")
    pair: ExchangeRatePair = Field(description="Currency pair.")
    rate: Decimal = Field(max_digits=18, decimal_places=6, description="Exchange rate.")
    source: str = Field(default="manual", max_length=50, description="Data source.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
