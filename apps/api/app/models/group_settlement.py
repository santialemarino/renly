from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Where a recorded settlement stands.
# 'pending' is money one member says they paid another. It COUNTS against the balance immediately —
# it really moved — and either named member may still delete it, which is what makes a marked-paid
# settlement reversible until confirmed.
# 'confirmed' is the payee acknowledging receipt, the trust anchor for real money; it locks the row
# until the payee un-confirms it.
# 'written_off' is a debt the creditor gave up on: it clears the same bucket a payment would, moves no
# cash at all, and is the other exit before a member with an open balance can be removed.
# There is deliberately no 'reversed' — reversing DELETES the row, exactly as revoking a group invite
# does, because until the audit log exists nothing would ever read a reversed state back.
class GroupSettlementStatus(StrEnum):
    confirmed = "confirmed"
    pending = "pending"
    written_off = "written_off"


# One recorded payment against a group's balances, and the only thing that clears them.
# Named apart from CardSettlement because the two are different acts on different ledgers and the
# per-account movement feed reads both — one word for both would make every call site ambiguous.
# ONE row is visible to both parties and updates both at once; never two entries to reconcile.
#
# Up to THREE amounts, each answering a different question:
#   * `amount`/`currency` is the BUCKET leg — which per-currency balance this cleared, and by how much.
#     Balances never net across currencies, so a settlement always names exactly one bucket;
#   * `from_amount` is what actually left the payer's own account, in THAT account's currency;
#   * `to_amount` is what actually arrived in the payee's, in theirs.
# Each cash figure is None when it equals `amount` — when no conversion happened — so the balance sums
# read coalesce(from_amount, amount), exactly as CardSettlement reads its account leg. Two legs rather
# than one because a settlement moves money between two DIFFERENT people's accounts. There is no
# stored rate: the pair of amounts IS the record of the rate used, and no single direction reads
# correctly both ways.
# Both account legs are optional — mark-as-paid naming no account is the v1 default, and a name-only
# member has no account to name at all.
class GroupSettlement(SQLModel, table=True):
    __tablename__ = "group_settlements"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group whose balances this clears.")
    from_member_id: int = Field(foreign_key="group_members.id", description="The seat paying.")
    to_member_id: int = Field(foreign_key="group_members.id", description="The seat being paid.")
    date: date_type = Field(description="Date the payment happened.")
    amount: Decimal = Field(max_digits=18, decimal_places=2, description="Amount cleared off the bucket.")
    currency: str = Field(max_length=3, description="The bucket's currency, not either account's.")
    status: GroupSettlementStatus = Field(
        default=GroupSettlementStatus.pending,
        sa_column=Column(SAEnum(GroupSettlementStatus, name="group_settlement_status"), nullable=False, server_default="pending"),
    )
    from_account_id: int | None = Field(default=None, foreign_key="accounts.id", description="Account the payer drew from.")
    from_amount: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=2, description="What left that account, in its currency. None when no conversion happened."
    )
    to_account_id: int | None = Field(default=None, foreign_key="accounts.id", description="Account the payee received into.")
    to_amount: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=2, description="What arrived there, in its currency. None when no conversion happened."
    )
    confirmed_at: datetime | None = Field(default=None, description="When the payee acknowledged receipt; set in exactly the confirmed status.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_by: int | None = Field(default=None, foreign_key="users.id", description="Who recorded it; NULL once that account is deleted.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
