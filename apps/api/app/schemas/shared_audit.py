# Response schemas for a group's audit trail (HTTP contract).

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.shared_audit import AuditAction, AuditEntityType


# Response for GET /groups/{group_id}/activity.
#
# It carries no sentence, only the parts of one: `entity_type` and `action` name a translation key and
# `payload` holds what that key interpolates, exactly as a notification row does. The web composes the
# prose, so the same entry reads correctly for two members using two different languages.
#
# `actor_name` is the one value resolved server-side, because it comes from the group's roster rather
# than the entry, and NULL means the seat no longer names an account — the reader's own copy says
# "someone" rather than leaving a hole in the middle of a sentence.
class SharedAuditEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Entry id.")
    entity_type: AuditEntityType = Field(description="What kind of shared thing this is about.")
    entity_id: int | None = Field(default=None, description="Its id, or null for an entity keyed by the group itself.")
    action: AuditAction = Field(description="What was done to it.")
    pot_id: int | None = Field(default=None, description="Pot this concerns, when it concerns one; used to build the link.")
    actor_name: str | None = Field(default=None, description="Who did it, as the group names them; null once the seat has no account.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Values the copy interpolates.")
    created_at: datetime = Field(description="When it happened.")
