from datetime import datetime

from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Per-user app config (display currencies, default currency; expandable later).
class UserSettings(SQLModel, table=True):
    __tablename__ = "user_settings"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, description="Owner.")
    settings: dict = Field(
        default_factory=dict,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        description="JSON config (e.g. display_currencies, default_currency).",
    )
    updated_at: datetime = Field(default_factory=utcnow)
