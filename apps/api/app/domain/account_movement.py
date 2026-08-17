# Value objects for the per-account ledger (account_movement_service).

from datetime import date as date_type
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple


# What a ledger row is, from the account's point of view. Deliberately a PARTITION of the movements
# that reach an account rather than a list of source tables: a reconciliation's adjustment is stored
# as an ordinary income or expense row carrying account_reconciliation_id, but it is a true-up rather
# than money the user earned or spent, so it reads (and filters) as its own kind. A transfer is one
# kind in both directions — direction is the sign of the amount, the same way the transfers sub-table
# derives it — because a transfer can never touch the same account twice (from_account_id <>
# to_account_id), so an account sees at most one of its legs.
class MovementKind(StrEnum):
    adjustment = "adjustment"
    expense = "expense"
    income = "income"
    settlement = "settlement"
    transfer = "transfer"


# Which table a movement was read from. This is what IDENTIFIES a row — `kind` cannot, because the
# adjustment kind spans two tables whose id sequences are independent, so a reconciliation that
# posted an income adjustment and one that posted an expense adjustment really can collide on
# (kind, source_id). Also the anchor anything wanting to link back to the owning record would need.
class MovementSource(StrEnum):
    expense = "expense"
    income = "income"
    settlement = "settlement"
    transfer = "transfer"


# One movement in an account's ledger. `amount` is SIGNED in the account's own currency: positive
# put money in, negative took it out. There is no per-row currency because there cannot be one —
# every linked row is validated to match the account's currency and each transfer leg is stored in
# its own account's, so the whole ledger is denominated in the account's currency (carried once on
# the list response).
#
# `balance_after` is the account's balance immediately after this movement, or None when a filter is
# active: it stays arithmetically true under a filter, but consecutive visible rows would then differ
# by amounts the user cannot see, which reads as broken arithmetic.
#
# `counterparty` names the other side — the card a settlement paid, or the account a transfer moved
# to/from. Resolved server-side, like CardSettlementResponse.account_name and TransferResponse's
# names, so a row can still say what it is when the client's own lists fail to load or when the other
# side has since been archived.
class AccountMovement(NamedTuple):
    source: MovementSource
    source_id: int
    kind: MovementKind
    date: date_type
    amount: Decimal
    balance_after: Decimal | None = None
    category: str | None = None
    counterparty: str | None = None
    counterparty_amount: Decimal | None = None
    counterparty_currency: str | None = None
    notes: str | None = None


# A ledger row as the repository reads it: the movement, plus the running total the window function
# computed alongside it — Σ amounts from the newest row through this one. The service turns that into
# the `balance_after` the API exposes by undoing it against the account's current balance, so the
# union's projection shape never has to be read positionally outside the repository that built it.
class MovementRow(NamedTuple):
    movement: AccountMovement
    running_total: Decimal
