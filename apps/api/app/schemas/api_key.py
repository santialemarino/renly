# Request/response schemas for API key endpoints.

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /api-keys.
class ApiKeyCreate(RequestBase):
    name: str | None = Field(default=None, description="User-given label.", max_length=100)


# Response for GET /api-keys (does not include the raw key).
class ApiKeyResponse(BaseModel):
    id: int = Field(description="API key id.")
    name: str | None = Field(default=None, description="User-given label.")
    created_at: datetime = Field(description="Creation timestamp.")
    last_used_at: datetime | None = Field(default=None, description="Last usage timestamp.")
    is_active: bool = Field(description="Whether this key is active.")

    model_config = {"from_attributes": True}


# Response for POST /api-keys (includes the raw key, shown once).
class ApiKeyCreateResponse(BaseModel):
    id: int = Field(description="API key id.")
    name: str | None = Field(default=None, description="User-given label.")
    raw_key: str = Field(description="Raw API key (shown only once).")
    created_at: datetime = Field(description="Creation timestamp.")
    is_active: bool = Field(description="Whether this key is active.")
