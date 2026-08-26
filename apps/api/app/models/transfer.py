from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Movement of money between two accounts the user owns — the one movement type that is neither income
# nor an expense, because net worth does not change: the money leaves one pool and arrives in another.
# Both sides are recorded so a cross-currency transfer (buy/sell USD) captures the rate actually used:
# from_amount is in the source account's currency, to_amount in the destination's, and their ratio is
# the implied rate including the spread. For a same-currency transfer the two are equal — a bank fee is
# recorded as its own expense rather than shrinking the transfer, so "a transfer never changes net
# worth" stays a hard invariant. Paying someone ELSE is an expense, not a transfer.
class Transfer(SQLModel, table=True):
    __tablename__ = "transfers"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(
        default=None, foreign_key="users.id", description="Owner, denormalized from the two legs, which share one scope; NULL when a pot owns them."
    )
    pot_id: int | None = Field(default=None, foreign_key="pots.id", description="Pot that co-owns both legs; NULL when they are private.")
    from_account_id: int = Field(foreign_key="accounts.id", description="Account the money leaves.")
    to_account_id: int = Field(foreign_key="accounts.id", description="Account the money arrives in.")
    date: date_type = Field(description="Date the movement happened.")
    from_amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount debited, in the source account's currency.")
    to_amount: Decimal = Field(
        max_digits=18,
        decimal_places=2,
        description="Amount credited, in the destination account's currency. Equals from_amount within one currency.",
    )
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
