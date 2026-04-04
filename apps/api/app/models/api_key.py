from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# API key for external access (iOS Shortcut, automations).
class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    key_hash: str = Field(max_length=255, description="Bcrypt hash of the raw API key.")
    key_prefix: str = Field(max_length=8, description="First 8 chars of the raw key (for indexed lookup).")
    name: str | None = Field(default=None, max_length=100, description="User-given label.")
    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: datetime | None = Field(default=None, description="Last time this key was used.")
    is_active: bool = Field(default=True, description="Whether this key is active.")
