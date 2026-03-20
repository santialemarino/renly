# Request/response schemas for exchange rate endpoints (HTTP contract).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.exchange_rate import ExchangeRatePair


# Response for a single exchange rate entry.
class ExchangeRateResponse(BaseModel):
    id: int = Field(description="Rate id.")
    date: date_type = Field(description="Rate date.")
    pair: ExchangeRatePair = Field(description="Currency pair.")
    rate: Decimal = Field(description="Exchange rate.")
    source: str = Field(description="Data source (e.g. dolarapi, manual).")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Response for GET /exchange-rates/latest. Groups rates by pair.
class LatestRatesResponse(BaseModel):
    rates: list[ExchangeRateResponse] = Field(description="Latest rate for each pair.")
    last_update: date_type | None = Field(default=None, description="Most recent date across all pairs.")
