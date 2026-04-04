from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Credit card settlement (payment reducing card liability — not an expense).
class CardSettlement(SQLModel, table=True):
    __tablename__ = "card_settlements"

    id: int | None = Field(default=None, primary_key=True)
    credit_card_id: int = Field(foreign_key="credit_cards.id", description="Card being paid.")
    date: date_type = Field(description="Settlement date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount paid.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217).")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
