from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Installment plan (cuotas; e.g. TV Samsung 12x). Auto-generates one expense per cuota each month (Step 3).
class Installment(SQLModel, table=True):
    __tablename__ = "installments"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Installment plan name (e.g. TV Samsung).")
    total_amount: Decimal = Field(max_digits=18, decimal_places=2, description="Total purchase amount across all cuotas.")
    installment_amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount of each cuota.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217).")
    installments_count: int = Field(description="Total number of cuotas.")
    start_date: date_type = Field(description="Date of the first cuota.")
    current_installment: int = Field(default=1, description="Index of the next cuota to issue (1-based).")
    payment_method: str | None = Field(default=None, max_length=20, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(
        default=None, foreign_key="credit_cards.id", description="Credit card used (when payment_method = credit_card)."
    )
    is_active: bool = Field(default=True, description="Whether the installment plan is active (set false when fully paid).")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
