from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Long-lived, rotating refresh token for silent access-token renewal (AUTH-7 "remember me"). Issued
# alongside the access token at login and rotated single-use on every /auth/refresh: each refresh
# consumes the presented token and mints its successor in the same family. Like auth_tokens, only the
# SHA-256 hash of the high-entropy raw token is stored; the raw value lives only in the client. Re-
# presenting an already-consumed token outside a short grace window is treated as theft and revokes
# the whole family; a session_epoch bump (logout / password change / reset) invalidates every token
# minted before it.
class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner of the token.")
    token_hash: str = Field(max_length=64, unique=True, index=True, description="SHA-256 hex of the raw token.")
    family_id: str = Field(max_length=32, index=True, description="Rotation lineage from one login; reuse revokes the whole family.")
    session_epoch: int = Field(description="users.session_epoch at mint time; a later bump invalidates this token.")
    remember_me: bool = Field(description="Whether 'remember me' was checked; selects the (sliding) validity window.")
    expires_at: datetime = Field(description="Token is invalid after this instant.")
    consumed_at: datetime | None = Field(default=None, description="Set when rotated; re-presentation signals reuse.")
    revoked_at: datetime | None = Field(default=None, description="Set when the family is revoked (reuse detected).")
    created_at: datetime = Field(default_factory=utcnow)
