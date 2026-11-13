from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from app.models.exchange_rate import DollarRate
from app.models.utils import utcnow


# How a shared expense's total is divided between the members taking part. A record of what the user
# ASKED for, never of the result: the per-member figures live on the splits, so re-deriving is never
# needed and a later change to the rounding rule cannot restate an expense everyone already agreed.
class SplitMethod(StrEnum):
    equal = "equal"
    exact = "exact"
    percentage = "percentage"
    shares = "shares"


# The money settings a group holds in common. A sibling table rather than columns on `groups`, so the
# membership kernel keeps carrying who the people are and nothing about what they share — the property
# that lets a non-money module adopt it unchanged.
# One row per group, created with the group, so no read needs an "or the default" branch.
# There is deliberately no group display currency: balances sit in per-currency buckets that never net
# across currencies, the unified figure beside them converts to each VIEWER's own display currency,
# and a cross-currency settlement names the currency it was actually paid in.
class GroupMoneySettings(SQLModel, table=True):
    __tablename__ = "group_money_settings"

    group_id: int = Field(foreign_key="groups.id", primary_key=True)
    default_split_method: SplitMethod = Field(
        default=SplitMethod.equal,
        sa_column=Column(SAEnum(SplitMethod, name="split_method"), nullable=False, server_default="equal"),
    )
    auto_finalise_settlements: bool = Field(
        default=False,
        description="When true a recorded settlement is confirmed on the spot instead of waiting on the payee.",
    )
    # The one dollar rate the group settles at: how much of one currency's debt a payment in another
    # clears, and the "at today's rate" figure beside a balance. One rate for everybody, because both
    # sides of a debt must agree on what a payment cleared; only a member's own display conversion
    # follows their personal preference.
    dollar_rate: DollarRate = Field(
        default=DollarRate.mep,
        sa_column=Column(SAEnum(DollarRate, name="dollar_rate", create_type=False), nullable=False, server_default="mep"),
    )
    # The one pending change of that rate: it takes every active member's agreement, and nothing changes
    # until all of them have given it. `dollar_rate_agreed_by` holds the seats that have agreed, the
    # proposer first.
    dollar_rate_proposal: DollarRate | None = Field(
        default=None, sa_column=Column(SAEnum(DollarRate, name="dollar_rate", create_type=False), nullable=True)
    )
    dollar_rate_proposed_by: int | None = Field(default=None, foreign_key="group_members.id", description="Seat that proposed the pending rate.")
    dollar_rate_agreed_by: list[int] = Field(default_factory=list, sa_column=Column(ARRAY(BigInteger), nullable=False, server_default="{}"))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
