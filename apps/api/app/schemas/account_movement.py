# Response schemas for the per-account ledger (GET /accounts/{id}/movements).

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.account_movement import MovementKind, MovementSource


# One row of the ledger. `amount` is signed in the account's currency (positive in, negative out), so
# a reader never has to know which kinds subtract; `source_id` is the id of the row in ITS OWN table
# and is therefore only unique per kind.
class AccountMovementResponse(BaseModel):
    source: MovementSource = Field(description="Table the movement was read from; with source_id it identifies the row.")
    source_id: int = Field(description="Id of the underlying row, unique only within its source.")
    kind: MovementKind = Field(description="What the movement is, from the account's point of view.")
    date: date_type = Field(description="Date the movement is dated.")
    amount: Decimal = Field(description="Signed amount in the account's currency: positive in, negative out.", max_digits=18, decimal_places=2)
    balance_after: Decimal | None = Field(
        default=None,
        description="Account balance immediately after this movement. Null while a kind filter is active.",
        max_digits=18,
        decimal_places=2,
    )
    category: str | None = Field(default=None, description="Entry category, for income / expense / adjustment rows.")
    counterparty: str | None = Field(default=None, description="Card paid, or the other account of a transfer.")
    counterparty_amount: Decimal | None = Field(
        default=None,
        description="The other side's amount, for a transfer. Differs from `amount` only across currencies.",
        max_digits=18,
        decimal_places=2,
    )
    counterparty_currency: str | None = Field(default=None, description="The other account's currency, for a transfer.")
    notes: str | None = Field(default=None, description="Optional notes carried by the underlying row.")

    model_config = {"from_attributes": True}


# A page of the ledger. `currency` is carried once rather than per row because it cannot vary: every
# linked entry is validated to match the account's currency, and each transfer leg is stored in its
# own account's — so the whole ledger is denominated in the account's currency.
class AccountMovementListResponse(BaseModel):
    items: list[AccountMovementResponse] = Field(description="Movements on this page, newest first.")
    total: int = Field(description="Total movements matching the filter.")
    page: int = Field(description="Current page (1-based).")
    page_size: int = Field(description="Items per page.")
    currency: str = Field(description="Currency every movement is denominated in (the account's).")

    model_config = {"from_attributes": True}
