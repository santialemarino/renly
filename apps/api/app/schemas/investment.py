# Request/response schemas for investment endpoints (HTTP contract).

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.investment import InvestmentCategory


# Minimal group info embedded in investment responses.
class InvestmentGroupInfo(BaseModel):
    id: int = Field(description="Group id.")
    name: str = Field(description="Group name.")

    model_config = {"from_attributes": True}


# Body for POST /investments. Creates a new investment.
class InvestmentCreate(BaseModel):
    name: str = Field(description="Display name of the investment.", max_length=255)
    category: InvestmentCategory = Field(description="Investment type (e.g. cedears, fci).")
    base_currency: str = Field(description="Reporting currency (ISO 4217 code).", max_length=10)
    ticker: str | None = Field(default=None, description="Symbol for auto-price-fetching (e.g. AAPL).", max_length=20)
    broker: str | None = Field(default=None, description="Broker or account name.", max_length=100)
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for PUT /investments/{id}. Partial update; only provided fields are updated.
class InvestmentUpdate(BaseModel):
    name: str | None = Field(default=None, description="Display name.", max_length=255)
    category: InvestmentCategory | None = Field(default=None, description="Investment type.")
    base_currency: str | None = Field(default=None, description="Reporting currency (ISO 4217 code).", max_length=10)
    ticker: str | None = Field(default=None, description="Symbol for auto-price-fetching.", max_length=20)
    broker: str | None = Field(default=None, description="Broker or account name.", max_length=100)
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for PUT /investments/{id}/groups. Replaces group membership for this investment.
class InvestmentSetGroupsBody(BaseModel):
    group_ids: list[int] = Field(
        description="Group ids to assign to this investment. Replaces existing membership.",
    )


# Response for GET list and GET one, POST and PUT. Exposes investment without user_id.
class InvestmentResponse(BaseModel):
    id: int = Field(description="Investment id.")
    name: str = Field(description="Display name.")
    category: InvestmentCategory = Field(description="Investment type.")
    base_currency: str = Field(description="Reporting currency (ISO 4217 code).")
    ticker: str | None = Field(default=None, description="Symbol for auto-price-fetching.")
    broker: str | None = Field(default=None, description="Broker or account name.")
    notes: str | None = Field(default=None, description="Optional notes.")
    is_active: bool = Field(description="Whether included in portfolio.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    groups: list[InvestmentGroupInfo] = Field(
        default_factory=list,
        description="Groups this investment belongs to.",
    )

    model_config = {"from_attributes": True}


# Response for GET /investments (paginated list with filters).
class InvestmentListResponse(BaseModel):
    items: list[InvestmentResponse] = Field(description="Investments on this page.")
    total: int = Field(description="Total matching investments (across all pages).")
    page: int = Field(description="Current page number (1-based).")
    page_size: int = Field(description="Number of items per page.")
