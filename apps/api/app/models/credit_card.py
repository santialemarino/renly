from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# User-owned credit card (liability account).
class CreditCard(SQLModel, table=True):
    __tablename__ = "credit_cards"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=100, description="Card label (e.g. Visa BBVA).")
    closing_day: int = Field(description="Statement closing day (1-31).")
    due_day: int = Field(description="Payment due day (1-31).")
    currency: str = Field(max_length=3, description="Card currency (ISO 4217).")
    is_active: bool = Field(default=True, description="Whether the card is active.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
