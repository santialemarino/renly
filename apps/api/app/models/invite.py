from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Lifecycle of an admin invite: pending until accepted, accepted once the invited address registers,
# revoked when an admin cancels it. An expired link is a pending invite past expires_at (derived, not stored).
class InviteStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


# Single-use admin invite binding a signup link to one email (invite-only access gate). An admin
# creates one per address; only the SHA-256 hash of the high-entropy raw token is stored (the raw
# value lives only in the emailed link, like auth_tokens). The token is consumed when the invited
# address completes registration, and rotates on resend. One active invite per email (unique).
class Invite(SQLModel, table=True):
    __tablename__ = "invites"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True, description="Invited email (lowercased); one invite per address.")
    token_hash: str = Field(max_length=64, unique=True, index=True, description="SHA-256 hex of the raw invite token.")
    invited_by: int = Field(foreign_key="users.id", description="Admin who created the invite.")
    status: InviteStatus = Field(sa_column=Column(SAEnum(InviteStatus, name="invite_status"), nullable=False, server_default="pending"))
    expires_at: datetime = Field(description="Invite link is invalid after this instant.")
    consumed_at: datetime | None = Field(default=None, description="Set when the invite is accepted (registration completed); enforces single-use.")
    created_at: datetime = Field(default_factory=utcnow)
