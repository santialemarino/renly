from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


# User-defined group for aggregating investments (e.g. Retirement, Kids, Trading).
class InvestmentGroup(SQLModel, table=True):
    __tablename__ = "investment_groups"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Display name of the group.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Many-to-many: an investment can belong to zero, one, or several groups.
class InvestmentGroupMember(SQLModel, table=True):
    __tablename__ = "investment_group_members"

    investment_id: int = Field(
        foreign_key="investments.id",
        primary_key=True,
        description="Investment in this group.",
    )
    group_id: int = Field(
        foreign_key="investment_groups.id",
        primary_key=True,
        description="Group this investment belongs to.",
    )
