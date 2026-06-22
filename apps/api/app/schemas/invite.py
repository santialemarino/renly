# Request/response schemas for the admin invite endpoints (HTTP contract).

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.schemas.base import RequestBase

# Validated email lowercased so an invite binds to a single canonical address.
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


# Body for POST /admin/invites. Creates (or re-arms) an invite for an email and sends the link.
class CreateInviteRequest(RequestBase):
    email: NormalizedEmail = Field(description="Email to invite (normalized to lowercase).")


# Response for the admin invite endpoints (list, create, resend, revoke). status is the effective
# status — a pending invite past its expiry reads as "expired" (pending / accepted / revoked / expired).
class InviteResponse(BaseModel):
    id: int = Field(description="Invite id.")
    email: str = Field(description="Invited email.")
    status: str = Field(description="Effective status: pending, accepted, revoked, or expired.")
    invited_by: int = Field(description="Id of the admin who created the invite.")
    expires_at: datetime = Field(description="When the current invite link expires.")
    consumed_at: datetime | None = Field(default=None, description="When the invite was accepted (null if not yet).")
    created_at: datetime = Field(description="When the invite was first created.")
