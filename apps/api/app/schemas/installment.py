# Request/response schemas for installment endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field, model_validator

from app.domain.payment_method import PaymentMethod, ensure_payment_pairing
from app.schemas.base import RequestBase
from app.utils.dates import add_months


# Body for POST /installments.
class InstallmentCreate(RequestBase):
    name: str = Field(description="Installment plan name (e.g. TV Samsung).", max_length=255)
    total_amount: Decimal = Field(description="Total purchase amount across all installments.", gt=0, max_digits=18, decimal_places=2)
    installment_amount: Decimal = Field(description="Amount of each installment.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    installments_count: int = Field(description="Total number of installments.", ge=1)
    start_date: date_type = Field(description="Date of the first installment.")
    current_installment: int = Field(default=1, description="Index of the next installment to issue (1-based).", ge=1)
    payment_method: PaymentMethod | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")

    # credit_card_id only pairs with the credit_card method. The reverse is NOT required —
    # a card-less credit_card entry is allowed (zero-card users, imports).
    @model_validator(mode="after")
    def validate_payment_pairing(self) -> "InstallmentCreate":
        ensure_payment_pairing(self.payment_method, self.credit_card_id)
        return self


# Body for PUT /installments/{id}. Partial update.
class InstallmentUpdate(RequestBase):
    name: str | None = Field(default=None, description="Installment plan name.", max_length=255)
    total_amount: Decimal | None = Field(default=None, description="Total purchase amount.", gt=0, max_digits=18, decimal_places=2)
    installment_amount: Decimal | None = Field(default=None, description="Amount of each installment.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    installments_count: int | None = Field(default=None, description="Total number of installments.", ge=1)
    current_installment: int | None = Field(default=None, description="Index of the next installment to issue.", ge=1)
    payment_method: PaymentMethod | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool | None = Field(default=None, description="Whether the installment plan is active.")
    start_date: date_type | None = Field(default=None, description="Date of the first installment.")

    # Same-request pairing guard: only fires when BOTH keys were provided. The merged
    # effective check (request fields over the stored row) lives in the service.
    @model_validator(mode="after")
    def validate_payment_pairing(self) -> "InstallmentUpdate":
        provided = self.model_fields_set
        if "payment_method" in provided and "credit_card_id" in provided:
            ensure_payment_pairing(self.payment_method, self.credit_card_id)
        return self


# Response for a single installment. `next_cuota_date` is derived from `start_date +
# (current_installment - 1) months` via `add_months` (month-end clamping included) so
# the installments table can render the next-due-date the same way the subscriptions
# and payment-obligations tables do (`next_billing_date` / `next_due_date`). Returns
# None for archived plans (`current_installment > installments_count`) so the cell
# can degrade to "—" instead of displaying a misleading post-final date. The field
# is named `next_cuota_date` (rather than `next_installment_date`) for consistency
# with the existing API contract and DB sort key.
class InstallmentResponse(BaseModel):
    id: int = Field(description="Installment id.")
    name: str = Field(description="Installment plan name.")
    total_amount: Decimal = Field(description="Original total purchase amount.", max_digits=18, decimal_places=2)
    installment_amount: Decimal = Field(description="Original per-installment amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_total_amount: Decimal | None = Field(
        default=None, description="Total amount in the requested display currency.", max_digits=18, decimal_places=2
    )
    converted_installment_amount: Decimal | None = Field(
        default=None,
        description="Per-installment amount in the requested display currency.",
        max_digits=18,
        decimal_places=2,
    )
    installments_count: int = Field(description="Total number of installments.")
    start_date: date_type = Field(description="Date of the first installment.")
    current_installment: int = Field(description="Index of the next installment to issue (1-based).")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    is_active: bool = Field(description="Whether the installment plan is active.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}

    # Derived from start_date + (current_installment - 1) months. Computed Pydantic
    # field so callers don't have to re-derive it client-side; serialised under the
    # same JSON key as a stored field.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def next_cuota_date(self) -> date_type | None:
        if self.current_installment > self.installments_count:
            return None
        return add_months(self.start_date, self.current_installment - 1)
