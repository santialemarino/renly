# Request/response schemas for investment snapshot endpoints (HTTP contract).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.investment import Currency
from app.schemas.base import RequestBase


# Body for POST /investments/{id}/snapshots. Creates or updates snapshot for that date.
class SnapshotCreate(RequestBase):
    date: date_type = Field(description="Snapshot date (e.g. month-end).")
    value: Decimal = Field(description="Total value on this date.", max_digits=18, decimal_places=2)
    quantity: Decimal | None = Field(default=None, description="Shares/units.", max_digits=18, decimal_places=6)
    currency: Currency = Field(description="Currency of the value.")
    notes: str | None = Field(default=None, description="Optional notes.")


# Response for GET list and POST. One snapshot per investment per date.
class SnapshotResponse(BaseModel):
    id: int = Field(description="Snapshot id.")
    investment_id: int = Field(description="Parent investment id.")
    date: date_type = Field(description="Snapshot date.")
    value: Decimal = Field(description="Value on this date.")
    quantity: Decimal | None = Field(default=None, description="Number of shares/units.")
    currency: Currency = Field(description="Currency of the value.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
