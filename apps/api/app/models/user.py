from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# User plan tier (monetization seam; free at launch, pro reserved for paid features).
class UserPlan(StrEnum):
    free = "free"
    pro = "pro"


# User account; auth via password_hash and session_epoch for token invalidation.
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, description="Display name.")
    email: str = Field(max_length=255, unique=True, description="Unique email.")
    password_hash: str = Field(max_length=255, description="Bcrypt hash.")
    session_epoch: int = Field(default=0, description="Bumped on logout; JWT must match.")
    plan: UserPlan = Field(sa_column=Column(SAEnum(UserPlan, name="user_plan"), nullable=False, server_default="free"))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
