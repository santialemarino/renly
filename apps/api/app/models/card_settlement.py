from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Credit card settlement (payment reducing card liability — not an expense). Carries up to two amounts:
# `amount`/`currency` are the CARD leg (what the payment cleared off the bucket), and `account_amount`
# the CASH leg in the funding account's own currency, set only when paying across currencies. The pair
# is the record of the rate used — there is deliberately no stored rate, the same reason Transfer has
# no implied_rate: no single direction reads correctly both ways and the division is unbounded.
class CardSettlement(SQLModel, table=True):
    __tablename__ = "card_settlements"

    id: int | None = Field(default=None, primary_key=True)
    credit_card_id: int = Field(foreign_key="credit_cards.id", description="Card being paid.")
    user_id: int = Field(foreign_key="users.id", description="Owner (denormalized from the parent credit card for row-level security).")
    date: date_type = Field(description="Settlement date.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount paid, clearing the card's bucket.")
    currency: str = Field(max_length=3, description="Currency (ISO 4217) — the bucket's, not the account's.")
    account_id: int | None = Field(default=None, foreign_key="accounts.id", description="Cash/bank account the payment was drawn from (optional).")
    account_amount: Decimal | None = Field(
        default=None,
        max_digits=18,
        decimal_places=2,
        description="What left the funding account, in that account's currency. None when no conversion happened.",
    )
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
