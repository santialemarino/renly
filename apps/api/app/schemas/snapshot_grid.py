# Request/response schemas for the snapshots grid endpoint (HTTP contract).

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.investment import InvestmentCategory


# Transaction details embedded in a grid cell (latest transaction in the period, if any).
class SnapshotGridTransaction(BaseModel):
    id: int = Field(description="Transaction id.")
    amount: Decimal = Field(description="Transaction amount (display currency).")
    original_amount: Decimal = Field(description="Transaction amount (base currency, for editing).")
    type: str = Field(description="Transaction kind (buy, sell, deposit, withdrawal).")


# One cell in the snapshots grid (a snapshot for an investment on a given date).
class SnapshotGridCell(BaseModel):
    date: date_type = Field(description="Snapshot date.")
    value: Decimal = Field(description="Snapshot value (display currency).")
    original_value: Decimal = Field(description="Snapshot value (base currency, for editing).")
    period_return_pct: Decimal | None = Field(
        default=None, description="Period return vs previous snapshot (null for first)."
    )
    has_transaction: bool = Field(description="Whether a transaction occurred in this period.")
    transaction: SnapshotGridTransaction | None = Field(
        default=None, description="Latest transaction in this period (null if none)."
    )


# One row in the snapshots grid (an investment with its snapshot cells).
class SnapshotGridRow(BaseModel):
    investment_id: int = Field(description="Investment id.")
    name: str = Field(description="Investment name.")
    category: InvestmentCategory = Field(description="Investment category.")
    base_currency: str = Field(description="Investment currency.")
    cells: list[SnapshotGridCell] = Field(default_factory=list, description="Snapshot cells sorted by date.")


# Response for GET /snapshots/grid.
class SnapshotGridResponse(BaseModel):
    rows: list[SnapshotGridRow] = Field(description="One row per investment.")
    months: list[date_type] = Field(description="All unique snapshot dates across investments, sorted ascending.")
