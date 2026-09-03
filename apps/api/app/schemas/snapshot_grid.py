# Request/response schemas for the snapshots grid endpoint (HTTP contract).

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.investment import InvestmentCategory
from app.models.pot import PotCadence
from app.schemas.list_scope import ListSectionResponse
from app.schemas.metrics import SkippedInvestment


# Transaction details embedded in a grid cell (latest transaction in the period, if any).
class SnapshotGridTransaction(BaseModel):
    id: int = Field(description="Transaction id.")
    amount: Decimal = Field(description="Transaction amount (display currency).")
    original_amount: Decimal = Field(description="Transaction amount (base currency, for editing).")
    quantity: Decimal | None = Field(default=None, description="Number of shares/units transacted.")
    type: str = Field(description="Transaction kind (buy, sell, deposit, withdrawal).")


# One cell in the snapshots grid (a snapshot for an investment on a given date).
#
# `column` is the grid column the snapshot falls in — the last day of its month, or the Sunday that
# closes its week. Resolved on the server so the interval rule lives in ONE place (domain.pot_monitoring,
# which the pot page's own value series is measured on) rather than being re-derived in the browser,
# where the two would have to agree about which week a Wednesday belongs to.
#
# Several snapshots can share a column; the grid renders the latest of them and the rest stay in `cells`
# so the form still knows every date that is taken.
class SnapshotGridCell(BaseModel):
    date: date_type = Field(description="Snapshot date.")
    column: date_type = Field(description="Period end this snapshot is bucketed into (month end, or the week's Sunday).")
    value: Decimal = Field(description="Snapshot value (display currency).")
    original_value: Decimal = Field(description="Snapshot value (base currency, for editing).")
    quantity: Decimal | None = Field(default=None, description="Number of shares/units.")
    source: str = Field(description="Origin: manual or auto.")
    period_return_pct: Decimal | None = Field(default=None, description="Period return vs previous snapshot (null for first).")
    has_transaction: bool = Field(description="Whether a transaction occurred in this period.")
    transaction: SnapshotGridTransaction | None = Field(default=None, description="Latest transaction in this period (null if none).")


# One row in the snapshots grid (an investment with its snapshot cells).
#
# The scope fields carry the pot ID only; the pot's LABEL lives on the section, stated once. `cadence`
# and `is_overdue` are the freshness indicator §8.2 asks for and are per ROW rather than per section: the
# cadence belongs to the pot, but whether a valuation is late depends on THIS holding's latest snapshot.
# Both are null/false on a private row, which declares no rhythm to be late against.
class SnapshotGridRow(BaseModel):
    investment_id: int = Field(description="Investment id.")
    name: str = Field(description="Investment name.")
    category: InvestmentCategory = Field(description="Investment category.")
    base_currency: str = Field(description="Investment currency.")
    ticker: str | None = Field(default=None, description="Ticker symbol (null if not ticker-linked).")
    cedear_ratio: Decimal | None = Field(default=None, description="CEDEARs per 1 underlying share.")
    scope: str = Field(default="private", description="'private' when the caller owns it, 'shared' when a pot they co-own does.")
    pot_id: int | None = Field(default=None, description="Pot holding it; null on a private row. Joins the row to its section.")
    cadence: PotCadence | None = Field(default=None, description="The owning pot's re-valuation cadence; null on a private row.")
    is_overdue: bool = Field(default=False, description="Whether this holding's latest snapshot is behind its pot's cadence.")
    cells: list[SnapshotGridCell] = Field(default_factory=list, description="Snapshot cells sorted by date.")


# Response for GET /snapshots/grid.
class SnapshotGridResponse(BaseModel):
    rows: list[SnapshotGridRow] = Field(description="One row per investment, in scope-major order.")
    columns: list[date_type] = Field(
        description=(
            "The grid's columns, ascending: one period end per bucket from the oldest snapshot's period "
            "through the newest's, with no gaps. Capped at the most recent columns, which is what makes "
            "the weekly interval usable over a long history."
        )
    )
    interval: str = Field(description="The grid the columns are measured on: 'monthly' or 'weekly'.")
    sections: list[ListSectionResponse] = Field(
        default_factory=list,
        description="The grid's scope sections in row order. Empty for a caller who can see no pot.",
    )
    skipped_investments: list[SkippedInvestment] = Field(
        default_factory=list,
        description="Investments excluded because their base currency can't be converted to the requested display currency.",
    )
