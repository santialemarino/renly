from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Who may see a pot, for a member with no explicit permission row of their own.
class PotVisibility(StrEnum):
    members = "members"
    owners = "owners"


# What an entry in a pot's ownership ledger records.
class OwnershipEventType(StrEnum):
    contribution = "contribution"
    opening = "opening"
    reagreement = "reagreement"
    withdrawal = "withdrawal"


# The container co-ownership attaches to: holdings point at it, and one ownership ledger divides the
# whole of it. Ownership lives here and never on the holding, so an internal rebalance (sell A, buy B)
# does not touch ownership at all.
class Pot(SQLModel, table=True):
    __tablename__ = "pots"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group whose members can reach this pot.")
    name: str | None = Field(default=None, max_length=255, description="NULL for a group's default pot, which the UI does not name.")
    base_currency: str = Field(max_length=3, description="Currency all ownership math runs in (ISO 4217).")
    visibility: PotVisibility = Field(
        default=PotVisibility.members,
        sa_column=Column(SAEnum(PotVisibility, name="pot_visibility"), nullable=False, server_default="members"),
    )
    is_default: bool = Field(default=False, description="The group's first pot, created with it.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# One member's access to one pot, overriding the pot's visibility default and carrying the only
# source of write access. Membership is not ownership: a member holding 0% may still see everything.
class PotMemberPermission(SQLModel, table=True):
    __tablename__ = "pot_member_permissions"

    pot_id: int = Field(foreign_key="pots.id", primary_key=True)
    member_id: int = Field(foreign_key="group_members.id", primary_key=True)
    can_view: bool = Field(default=True, description="Whether this seat may see the pot at all.")
    can_write: bool = Field(default=False, description="Whether this seat may record movements; implies can_view.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# One dated entry in a pot's ownership ledger. Balances are derived by replaying these in order —
# nothing is stored as a running total.
# `units` is ALWAYS the signed change to member_id's balance and never varies its meaning by type; a
# reagreement's counterparty receives exactly the negation, which is what makes it net-zero by
# construction. amount/amount_currency/base_amount carry both sides of a cross-currency move and
# never a derived rate, matching transfers and card_settlements.
# from_account_id / to_account_id make the event a real MOVEMENT rather than a note about one: the
# per-account balance union reads both legs, so a contribution genuinely leaves the mover's account
# and arrives in one the pot holds. This is the transfer mechanic at a different scope.
class PotOwnershipEvent(SQLModel, table=True):
    __tablename__ = "pot_ownership_events"

    id: int | None = Field(default=None, primary_key=True)
    pot_id: int = Field(foreign_key="pots.id", description="Pot whose ownership this moves.")
    type: OwnershipEventType = Field(sa_column=Column(SAEnum(OwnershipEventType, name="ownership_event_type"), nullable=False))
    date: date_type = Field(description="Date the movement is priced at.")
    member_id: int = Field(foreign_key="group_members.id", description="The seat whose units change.")
    counterparty_member_id: int | None = Field(
        default=None,
        foreign_key="group_members.id",
        description="Reagreement only: the seat receiving the negation of units.",
    )
    amount: Decimal | None = Field(default=None, max_digits=18, decimal_places=2, description="Money moved, in its source currency.")
    amount_currency: str | None = Field(default=None, max_length=3, description="Source currency; NULL when it equals the pot's.")
    base_amount: Decimal | None = Field(default=None, max_digits=18, decimal_places=2, description="Credited amount in the pot's base currency.")
    units: Decimal = Field(max_digits=18, decimal_places=6, description="Signed change to member_id's unit balance.")
    unit_price: Decimal = Field(max_digits=18, decimal_places=6, description="The price used, recorded because NAV moves as later snapshots arrive.")
    from_account_id: int | None = Field(
        default=None, foreign_key="accounts.id", description="Account debited: the mover's private one on a contribution."
    )
    to_account_id: int | None = Field(default=None, foreign_key="accounts.id", description="Account credited: one the pot holds on a contribution.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_by: int | None = Field(default=None, foreign_key="users.id", description="Who recorded it; NULL once that account is deleted.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
