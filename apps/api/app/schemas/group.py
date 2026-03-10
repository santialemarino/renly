# Request/response schemas for group endpoints (HTTP contract).

from datetime import datetime

from pydantic import BaseModel, Field


# Body for POST /groups. Creates a new group.
class GroupCreate(BaseModel):
    name: str = Field(description="Display name of the group.", max_length=255)


# Body for PUT /groups/{id}. Partial update; only provided fields are updated.
class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, description="Display name of the group.", max_length=255)


# Response for GET list and GET one, POST and PUT. Exposes group with optional member count or ids.
class GroupResponse(BaseModel):
    id: int = Field(description="Group id.")
    name: str = Field(description="Display name of the group.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    investment_ids: list[int] = Field(
        default_factory=list,
        description="Ids of investments in this group (included when requested).",
    )

    model_config = {"from_attributes": True}


# Body for PUT /groups/{id}/investments. Replaces membership with the given list.
class GroupSetInvestmentsBody(BaseModel):
    investment_ids: list[int] = Field(
        description="Investment ids in this group. Replaces existing membership.",
    )
