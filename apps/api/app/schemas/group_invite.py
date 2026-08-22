# Request/response schemas for group-seat invite endpoints (HTTP contract).

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.group import GroupKind
from app.schemas.base import RequestBase


# Body for POST /groups/{id}/members/{member_id}/invite. Creates the seat's invite, or rotates it when
# one already exists (a resend). Admin only. Omitting `email` produces a link-only invite: nothing is
# sent and the caller shares the returned URL themselves.
class GroupInviteCreate(RequestBase):
    email: str | None = Field(default=None, description="Address to email the link to. Omit for a link-only invite.", max_length=255)


# Response for POST /groups/{id}/members/{member_id}/invite. The raw token appears ONLY here, in the
# reply to the request that minted it — nothing stores it, so a lost link is re-sent by rotating.
class GroupInviteCreatedResponse(BaseModel):
    member_id: int = Field(description="Seat the invite claims.")
    email: str | None = Field(default=None, description="Address the link was emailed to; null for a link-only invite.")
    invite_url: str = Field(description="Shareable link that claims the seat. Shown once; rotate to get a new one.")
    expires_at: datetime = Field(description="Instant after which the link stops working.")


# Response for GET /group-invites/{token}. The pre-membership preview: what the recipient needs to
# decide whether to accept, and nothing more. Unauthenticated on purpose — the link's holder was given
# it deliberately, and requiring a session to even read it would strand anyone who arrives logged out.
class GroupInvitePreviewResponse(BaseModel):
    group_name: str = Field(description="Name of the group the invite is for.")
    group_kind: GroupKind = Field(description="What the group is for.")
    member_display_name: str = Field(description="How the seat is named in the group.")
    invited_by_name: str | None = Field(default=None, description="Name of whoever sent the invite; null if that account is gone.")
    expires_at: datetime = Field(description="Instant after which the link stops working.")


# Response for POST /group-invites/{token}/accept. Returns the group the caller just joined so the
# client can navigate straight to its hub.
class GroupInviteAcceptedResponse(BaseModel):
    group_id: int = Field(description="Group the caller just joined.")
    group_name: str = Field(description="Name of that group.")
    member_id: int = Field(description="Seat the caller now holds.")
