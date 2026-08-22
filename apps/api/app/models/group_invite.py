from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# A pending invitation to claim one group seat. Same mechanism as the platform Invite (high-entropy raw
# token, only its SHA-256 hash stored, time-limited, single-use via consumed_at, rotate-on-resend) but
# a separate entity: `invites` is globally unique per email because it gates platform signup, whereas
# the same person may hold seats in several groups at once — and a group invite grants no signup access.
# The token IS the credential: no account is created here, it only links an existing account to this
# seat, which is what makes a shareable link possible. `email` records where the link was sent (NULL
# for a link-only invite) and constrains nothing. Revoking deletes the row; there is no revoked state.
class GroupInvite(SQLModel, table=True):
    __tablename__ = "group_invites"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group the seat belongs to.")
    member_id: int = Field(foreign_key="group_members.id", unique=True, description="The seat being claimed; one live invite per seat.")
    email: str | None = Field(default=None, max_length=255, description="Address the link was sent to (lowercased); NULL for a link-only invite.")
    token_hash: str = Field(max_length=64, unique=True, index=True, description="SHA-256 hex of the raw invite token.")
    expires_at: datetime = Field(description="Invite link is invalid after this instant.")
    consumed_at: datetime | None = Field(default=None, description="Set when the seat is claimed; enforces single-use.")
    created_by: int | None = Field(default=None, foreign_key="users.id", description="Who sent the invite; NULL once that account is deleted.")
    created_at: datetime = Field(default_factory=utcnow)
