# Request/response schemas for collection endpoints (HTTP contract).

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /collections. Creates a new collection.
class CollectionCreate(RequestBase):
    name: str = Field(description="Display name of the collection.", max_length=255)
    target_percentage: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )


# Body for PUT /collections/{id}. Partial update; only provided fields are updated.
class CollectionUpdate(RequestBase):
    name: str | None = Field(default=None, description="Display name of the collection.", max_length=255)
    target_percentage: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )


# Response for GET list and GET one, POST and PUT. Exposes the collection with its member ids.
class CollectionResponse(BaseModel):
    id: int = Field(description="Collection id.")
    name: str = Field(description="Display name of the collection.")
    target_percentage: Decimal | None = Field(
        default=None,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    investment_ids: list[int] = Field(
        default_factory=list,
        description="Ids of investments in this collection (included when requested).",
    )

    model_config = {"from_attributes": True}


# Body for PUT /collections/{id}/investments. Replaces membership with the given list.
class CollectionSetInvestmentsBody(RequestBase):
    investment_ids: list[int] = Field(
        description="Investment ids in this collection. Replaces existing membership.",
    )
