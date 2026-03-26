from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


# User account; auth via password_hash and session_epoch for token invalidation.
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, description="Display name.")
    email: str = Field(max_length=255, unique=True, description="Unique email.")
    password_hash: str = Field(max_length=255, description="Bcrypt hash.")
    session_epoch: int = Field(default=0, description="Bumped on logout; JWT must match.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
