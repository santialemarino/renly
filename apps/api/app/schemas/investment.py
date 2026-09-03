# Request/response schemas for investment endpoints (HTTP contract).

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.investment import InvestmentCategory
from app.schemas.base import RequestBase, validate_supported_currency
from app.schemas.list_scope import ListSectionResponse


# Minimal collection info embedded in investment responses.
class InvestmentCollectionInfo(BaseModel):
    id: int = Field(description="Collection id.")
    name: str = Field(description="Collection name.")

    model_config = {"from_attributes": True}


# Body for POST /investments. Creates a new investment.
class InvestmentCreate(RequestBase):
    name: str = Field(description="Display name of the investment.", max_length=255)
    category: InvestmentCategory = Field(description="Investment type (e.g. cedears, fci).")
    base_currency: str = Field(description="Reporting currency (ISO 4217 code).", max_length=3)
    ticker: str | None = Field(default=None, description="Symbol for auto-price-fetching (e.g. AAPL).", max_length=20)
    broker: str | None = Field(default=None, description="Broker or account name.", max_length=100)
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    _validate_base_currency = field_validator("base_currency")(validate_supported_currency)


# Body for PUT /investments/{id}. Partial update; only provided fields are updated.
class InvestmentUpdate(RequestBase):
    name: str | None = Field(default=None, description="Display name.", max_length=255)
    category: InvestmentCategory | None = Field(default=None, description="Investment type.")
    base_currency: str | None = Field(default=None, description="Reporting currency (ISO 4217 code).", max_length=3)
    ticker: str | None = Field(default=None, description="Symbol for auto-price-fetching.", max_length=20)
    broker: str | None = Field(default=None, description="Broker or account name.", max_length=100)
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    _validate_base_currency = field_validator("base_currency")(validate_supported_currency)


# Body for PUT /investments/{id}/collections. Replaces collection membership for this investment.
class InvestmentSetCollectionsBody(RequestBase):
    collection_ids: list[int] = Field(
        description="Collection ids to assign to this investment. Replaces existing membership.",
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
    has_snapshots: bool = Field(description="Whether the investment has any snapshots. Used to lock currency changes.")
    scope: str = Field(default="private", description="'private' when the caller owns it, 'shared' when a pot they co-own does.")
    pot_id: int | None = Field(
        default=None,
        description="Pot holding it; null on a private row. Joins the row to its section, which carries the pot's label.",
    )
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    collections: list[InvestmentCollectionInfo] = Field(
        default_factory=list,
        description="Collections this investment belongs to.",
    )

    model_config = {"from_attributes": True}


# Response for GET /investments (paginated list with filters).
class InvestmentListResponse(BaseModel):
    items: list[InvestmentResponse] = Field(description="Investments on this page.")
    total: int = Field(description="Total matching investments (across all pages).")
    page: int = Field(description="Current page number (1-based).")
    page_size: int = Field(description="Number of items per page.")
    sections: list[ListSectionResponse] = Field(
        default_factory=list,
        description=(
            "The list's scope sections in row order, counted across every page. Holds only the private "
            "section for a user who can see no pot, and the totals are empty because this list shows no "
            "money column."
        ),
    )
