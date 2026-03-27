# CEDEAR-to-underlying conversion ratio (e.g. 10 AAPL.BA = 1 AAPL).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models.utils import utcnow


# Conversion ratio between a CEDEAR and its underlying stock.
class CedearRatio(SQLModel, table=True):
    __tablename__ = "cedear_ratios"
    __table_args__ = (UniqueConstraint("ticker", "effective_date"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(max_length=20, description="CEDEAR symbol (e.g. AAPL.BA).")
    underlying: str = Field(max_length=20, description="Underlying stock symbol (e.g. AAPL).")
    ratio: Decimal = Field(max_digits=10, decimal_places=4, description="CEDEARs per 1 underlying share.")
    effective_date: date_type = Field(description="Date this ratio became effective.")
    source: str = Field(default="manual", max_length=50, description="Data source.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
