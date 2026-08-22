# Request/response schemas for group and membership endpoints (HTTP contract).

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.group import GroupKind, GroupMemberRole
from app.schemas.base import RequestBase


# Body for POST /groups. The creator is seeded as the group's first admin member.
class GroupCreate(RequestBase):
    name: str = Field(description="Display name of the group.", max_length=255)
    kind: GroupKind = Field(description="What the group is for (household, couple, trip, flat, other).")
    display_name: str | None = Field(
        default=None,
        description="How the creator is shown in the group. Defaults to their account name.",
        max_length=255,
    )


# Body for PUT /groups/{id}. Partial update; only provided fields are updated. Admin only.
class GroupUpdate(RequestBase):
    name: str | None = Field(default=None, description="Display name of the group.", max_length=255)
    kind: GroupKind | None = Field(default=None, description="What the group is for.")


# Body for POST /groups/{id}/members. Adds a name-only seat — someone tracked in the group who has no
# Renly account yet. Inviting them is a separate action on the seat. Admin only.
class GroupMemberCreate(RequestBase):
    display_name: str = Field(description="How this person is shown in the group.", max_length=255)
    role: GroupMemberRole = Field(default=GroupMemberRole.member, description="Group administration role.")


# Body for PUT /groups/{id}/members/{member_id}. Partial update; only provided fields are updated.
# Admin only.
#
# `is_active` is typed Literal[True] rather than bool on purpose: it exists ONLY to bring a former
# member back. Removing someone is DELETE on this same path, which is the verb that also drops their
# pending invite and is the one a member may use on their own seat. Allowing `false` here would be a
# second, subtly different removal — and it had a real bug: an admin deactivating their own seat
# committed the change and then got a 404, because the response is rebuilt by re-reading a group the
# caller is no longer a member of. A `false` is now a 422 at the schema boundary, so there is no
# branch to keep in step.
class GroupMemberUpdate(RequestBase):
    display_name: str | None = Field(default=None, description="How this person is shown in the group.", max_length=255)
    role: GroupMemberRole | None = Field(default=None, description="Group administration role.")
    is_active: Literal[True] | None = Field(default=None, description="Pass true to reactivate a former member. Use DELETE to remove one.")


# Response for every member-carrying group endpoint. Exposes whether the seat is linked to an account
# (is_linked) and whether it is the requesting user's own (is_self) WITHOUT exposing anyone's user id —
# the id is of no use to a client and naming it would leak account identity across a group.
class GroupMemberResponse(BaseModel):
    id: int = Field(description="Member (seat) id.")
    display_name: str = Field(description="How this person is shown in the group.")
    role: GroupMemberRole = Field(description="Group administration role.")
    is_active: bool = Field(description="False for a former member; their history is kept.")
    is_linked: bool = Field(description="Whether a Renly account holds this seat (false = name-only placeholder).")
    is_self: bool = Field(description="Whether this seat belongs to the requesting user.")
    has_pending_invite: bool = Field(description="Whether a live, unexpired invite is outstanding for this seat.")
    joined_at: datetime | None = Field(default=None, description="When an account claimed this seat.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Response for GET list and GET one, POST and PUT. `members` carries every seat, active and former, so
# a client can render the roster without a second call. my_role is the requesting user's own role,
# which is what every admin-only control in the UI keys off.
class GroupResponse(BaseModel):
    id: int = Field(description="Group id.")
    name: str = Field(description="Display name of the group.")
    kind: GroupKind = Field(description="What the group is for.")
    my_role: GroupMemberRole = Field(description="The requesting user's role in this group.")
    active_member_count: int = Field(description="Number of seats currently active.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    members: list[GroupMemberResponse] = Field(default_factory=list, description="Every seat in the group, active and former.")

    model_config = {"from_attributes": True}
