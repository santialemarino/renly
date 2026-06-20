from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Purpose of a single-use auth token (email verification, password reset, or email change).
class AuthTokenType(StrEnum):
    email_verification = "email_verification"
    password_reset = "password_reset"
    email_change = "email_change"


# Single-use, time-limited token for account-lifecycle flows (AUTH-1/2/8). Only the SHA-256 hash of
# the high-entropy raw token is stored; the raw value lives only in the emailed link.
class AuthToken(SQLModel, table=True):
    __tablename__ = "auth_tokens"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner of the token.")
    token_hash: str = Field(max_length=64, unique=True, index=True, description="SHA-256 hex of the raw token.")
    token_type: AuthTokenType = Field(sa_column=Column(SAEnum(AuthTokenType, name="auth_token_type"), nullable=False, index=True))
    new_email: str | None = Field(default=None, max_length=255, description="Pending new address (email_change tokens only).")
    expires_at: datetime = Field(description="Token is invalid after this instant.")
    consumed_at: datetime | None = Field(default=None, description="Set when first used; enforces single-use.")
    created_at: datetime = Field(default_factory=utcnow)
