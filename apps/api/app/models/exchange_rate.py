from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models.utils import utcnow


# Exchange rate pair — all rates stored against USD.
class ExchangeRatePair(StrEnum):
    USD_ARS_OFICIAL = "USD_ARS_OFICIAL"
    USD_ARS_MEP = "USD_ARS_MEP"
    USD_ARS_BLUE = "USD_ARS_BLUE"
    USD_BRL = "USD_BRL"
    USD_EUR = "USD_EUR"
    USD_GBP = "USD_GBP"


# Daily exchange rate for a pair (one row per date per pair).
class ExchangeRate(SQLModel, table=True):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("date", "pair"),)

    id: int | None = Field(default=None, primary_key=True)
    date: date_type = Field(description="Rate date.")
    pair: ExchangeRatePair = Field(
        sa_column=Column(SAEnum(ExchangeRatePair, name="exchange_rate_pair"), nullable=False)
    )
    rate: Decimal = Field(max_digits=18, decimal_places=6, description="Exchange rate.")
    source: str = Field(default="manual", max_length=50, description="Data source.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
