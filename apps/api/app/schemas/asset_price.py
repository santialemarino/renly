# Request/response schemas for asset price endpoints (HTTP contract).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# Response for a single asset price entry.
class AssetPriceResponse(BaseModel):
    id: int = Field(description="Asset price id.")
    ticker: str = Field(description="Asset symbol.")
    date: date_type = Field(description="Price date.")
    price: Decimal = Field(description="Closing price.")
    currency: str = Field(description="Price currency.")
    source: str = Field(description="Data provider.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Response for the refresh endpoint.
class RefreshPricesResponse(BaseModel):
    prices_stored: int = Field(description="Number of prices fetched and stored.")
