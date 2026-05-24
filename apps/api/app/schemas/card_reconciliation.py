# Request/response schemas for card reconciliation endpoints (Phase 3, Step 5).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /credit-cards/{id}/reconciliations. Creates a fresh reconciliation
# or replaces an existing one for the same (currency, period_start, period_end).
class CardReconciliationCreate(RequestBase):
    currency: str = Field(description="Bucket currency (ISO 4217).", max_length=3)
    period_start: date_type = Field(description="Inclusive first day of the statement period.")
    period_end: date_type = Field(description="Inclusive closing date of the statement period.")
    statement_balance: Decimal = Field(
        description="Bank's actual statement balance from the resumen.",
        max_digits=18,
        decimal_places=2,
    )


# Response for a single reconciliation. Returned by GET, POST, and the latest-per-bucket endpoint.
class CardReconciliationResponse(BaseModel):
    id: int = Field(description="Reconciliation id.")
    card_id: int = Field(description="Card id.")
    currency: str = Field(description="Bucket currency (ISO 4217).")
    period_start: date_type = Field(description="Inclusive first day of the statement period.")
    period_end: date_type = Field(description="Inclusive closing date of the statement period.")
    statement_balance: Decimal = Field(description="Bank's actual statement balance.", max_digits=18, decimal_places=2)
    computed_balance: Decimal = Field(description="Running balance at period_end at reconciliation time.", max_digits=18, decimal_places=2)
    difference: Decimal = Field(description="statement_balance - computed_balance.", max_digits=18, decimal_places=2)
    adjustment_expense_id: int | None = Field(default=None, description="Adjustment expense id (set when difference > 0).")
    adjustment_income_id: int | None = Field(default=None, description="Adjustment income id (set when difference < 0).")
    is_stale: bool = Field(description="True when a relevant edit inside the period happened after reconciliation.")
    reconciled_at: datetime = Field(description="When the user ran the reconciliation.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# One entry in the GET /credit-cards/{id}/statements response — drives the Reconciliations sub-section UI.
# Each row is a recent statement period per bucket, computed by walking back N closing dates from today.
class StatementPeriodResponse(BaseModel):
    currency: str = Field(description="Bucket currency.")
    period_start: date_type = Field(description="Inclusive first day of the period.")
    period_end: date_type = Field(description="Inclusive closing date of the period.")
    computed_balance: Decimal = Field(description="Running balance at period_end (recomputed live).", max_digits=18, decimal_places=2)
    reconciliation: CardReconciliationResponse | None = Field(default=None, description="The reconciliation for this period, if any.")
