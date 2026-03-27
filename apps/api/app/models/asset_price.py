# Daily asset price for a ticker, fetched from external APIs.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models.utils import utcnow


# Historical price for a publicly traded asset (one per ticker per date).
class AssetPrice(SQLModel, table=True):
    __tablename__ = "asset_prices"
    __table_args__ = (UniqueConstraint("ticker", "date"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(max_length=20, description="Asset symbol (e.g. AAPL, BTC, AAPL.BA).")
    date: date_type = Field(description="Price date.")
    price: Decimal = Field(max_digits=18, decimal_places=6, description="Closing price.")
    currency: str = Field(max_length=10, description="Price currency (e.g. USD, ARS).")
    source: str = Field(default="manual", max_length=50, description="Data provider.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
