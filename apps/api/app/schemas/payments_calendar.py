# Request/response schemas for the Payments Calendar endpoint.

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


# One event on the Payments Calendar timeline.
# `type` discriminates the source entity: 'subscription' | 'installment' | 'obligation' | 'card_due'.
class PaymentsCalendarItemResponse(BaseModel):
    type: str = Field(description="Source entity type (subscription, installment, obligation, card_due).", max_length=20)
    date: date_type = Field(description="Event date (cuota / billing / due / card_due).")
    name: str = Field(description="Display label sourced from the underlying entity.")
    amount: Decimal = Field(description="Original amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_amount: Decimal | None = Field(
        default=None,
        description="Amount in the requested display currency.",
        max_digits=18,
        decimal_places=2,
    )
    payment_method: str | None = Field(default=None, description="Payment method when applicable.")
    credit_card_id: int | None = Field(default=None, description="Credit card id when applicable.")
    source_id: int = Field(description="Id of the underlying entity (subscription / installment / obligation / card).")
    cuota_index: int | None = Field(default=None, description="1-based cuota index (installments only).")
    installments_count: int | None = Field(default=None, description="Total cuotas (installments only).")
    recurrence: str | None = Field(default=None, description="Recurrence pattern (obligations only).")
    is_paid: bool = Field(
        default=False,
        description="True when an obligation cycle has a linked expense (Phase 3, Step E). Always False for non-obligation events.",
    )


# Response for GET /payments-calendar.
class PaymentsCalendarResponse(BaseModel):
    year: int = Field(description="Calendar year of the requested window.")
    month: int = Field(description="Calendar month of the requested window (1-12).")
    currency: str | None = Field(default=None, description="Display currency when conversion was requested.")
    items: list[PaymentsCalendarItemResponse] = Field(
        default_factory=list,
        description="Calendar events sorted by date ascending, stable within the same date.",
    )
