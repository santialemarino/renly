# Request/response schemas for group endpoints (HTTP contract).

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /groups. Creates a new group.
class GroupCreate(RequestBase):
    name: str = Field(description="Display name of the group.", max_length=255)
    target_percentage: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )


# Body for PUT /groups/{id}. Partial update; only provided fields are updated.
class GroupUpdate(RequestBase):
    name: str | None = Field(default=None, description="Display name of the group.", max_length=255)
    target_percentage: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )


# Response for GET list and GET one, POST and PUT. Exposes group with optional member count or ids.
class GroupResponse(BaseModel):
    id: int = Field(description="Group id.")
    name: str = Field(description="Display name of the group.")
    target_percentage: Decimal | None = Field(
        default=None,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    investment_ids: list[int] = Field(
        default_factory=list,
        description="Ids of investments in this group (included when requested).",
    )

    model_config = {"from_attributes": True}


# Body for PUT /groups/{id}/investments. Replaces membership with the given list.
class GroupSetInvestmentsBody(RequestBase):
    investment_ids: list[int] = Field(
        description="Investment ids in this group. Replaces existing membership.",
    )
