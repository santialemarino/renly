# Request/response schemas for installment endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /installments.
class InstallmentCreate(RequestBase):
    name: str = Field(description="Installment plan name (e.g. TV Samsung).", max_length=255)
    total_amount: Decimal = Field(description="Total purchase amount across all cuotas.", gt=0, max_digits=18, decimal_places=2)
    installment_amount: Decimal = Field(description="Amount of each cuota.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    installments_count: int = Field(description="Total number of cuotas.", ge=1)
    start_date: date_type = Field(description="Date of the first cuota.")
    current_installment: int = Field(default=1, description="Index of the next cuota to issue (1-based).", ge=1)
    payment_method: str | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")


# Body for PUT /installments/{id}. Partial update.
class InstallmentUpdate(RequestBase):
    name: str | None = Field(default=None, description="Installment plan name.", max_length=255)
    total_amount: Decimal | None = Field(default=None, description="Total purchase amount.", gt=0, max_digits=18, decimal_places=2)
    installment_amount: Decimal | None = Field(default=None, description="Amount of each cuota.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    installments_count: int | None = Field(default=None, description="Total number of cuotas.", ge=1)
    current_installment: int | None = Field(default=None, description="Index of the next cuota to issue.", ge=1)
    payment_method: str | None = Field(default=None, description="Payment method.", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool | None = Field(default=None, description="Whether the installment plan is active.")
    start_date: date_type | None = Field(default=None, description="Date of the first cuota.")


# Response for a single installment.
class InstallmentResponse(BaseModel):
    id: int = Field(description="Installment id.")
    name: str = Field(description="Installment plan name.")
    total_amount: Decimal = Field(description="Original total purchase amount.", max_digits=18, decimal_places=2)
    installment_amount: Decimal = Field(description="Original cuota amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_total_amount: Decimal | None = Field(
        default=None, description="Total amount in the requested display currency.", max_digits=18, decimal_places=2
    )
    converted_installment_amount: Decimal | None = Field(
        default=None,
        description="Cuota amount in the requested display currency.",
        max_digits=18,
        decimal_places=2,
    )
    installments_count: int = Field(description="Total number of cuotas.")
    start_date: date_type = Field(description="Date of the first cuota.")
    current_installment: int = Field(description="Index of the next cuota to issue (1-based).")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool = Field(description="Whether the installment plan is active.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
