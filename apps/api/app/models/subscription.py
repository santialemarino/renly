from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Recurring subscription (e.g. Netflix, Spotify, gym). Auto-generates monthly expenses (Step 3).
class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Subscription name (e.g. Netflix).")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Charge amount per billing cycle.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217).")
    billing_cycle: str = Field(max_length=20, description="Billing cycle (monthly, annual, quarterly, biweekly, weekly).")
    next_billing_date: date_type = Field(description="Date of next billing event.")
    payment_method: str | None = Field(default=None, max_length=20, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(
        default=None, foreign_key="credit_cards.id", description="Credit card used (when payment_method = credit_card)."
    )
    is_active: bool = Field(default=True, description="Whether the subscription is active.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
