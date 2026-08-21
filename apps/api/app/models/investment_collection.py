from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# User-defined collection for aggregating investments (e.g. Retirement, Kids, Trading).
class InvestmentCollection(SQLModel, table=True):
    __tablename__ = "investment_collections"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Display name of the collection.")
    target_percentage: Decimal | None = Field(
        default=None,
        max_digits=5,
        decimal_places=2,
        ge=0,
        le=100,
        description="Target allocation % for dashboard over/under-exposure alerts.",
    )
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# Many-to-many: an investment can belong to zero, one, or several collections.
class InvestmentCollectionMember(SQLModel, table=True):
    __tablename__ = "investment_collection_members"

    investment_id: int = Field(
        foreign_key="investments.id",
        primary_key=True,
        description="Investment in this collection.",
    )
    collection_id: int = Field(
        foreign_key="investment_collections.id",
        primary_key=True,
        description="Collection this investment belongs to.",
    )
