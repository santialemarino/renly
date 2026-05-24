from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Recurring or one-off payment obligation (e.g. electricity, ABL, internet). Surfaces in Payments Calendar.
class PaymentObligation(SQLModel, table=True):
    __tablename__ = "payment_obligations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Obligation name (e.g. Electricity).")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount due.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217).")
    next_due_date: date_type = Field(
        description="Anchor date for the next occurrence — recurring obligations project forward from this in the Payments Calendar.",
    )
    recurrence: str | None = Field(
        default=None, max_length=20, description="Recurrence pattern (monthly, bimonthly, quarterly, annual). None for one-off."
    )
    category: str | None = Field(default=None, max_length=100, description="Free-form obligation category (e.g. utilities, taxes).")
    payment_method: str | None = Field(default=None, max_length=20, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(
        default=None, foreign_key="credit_cards.id", description="Credit card used (when payment_method = credit_card)."
    )
    is_active: bool = Field(default=True, description="Whether the obligation is active.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
