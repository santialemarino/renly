# Request/response schemas for auth endpoints (HTTP contract).

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.models.user import UserPlan
from app.schemas.base import RequestBase

# Minimum password length enforced at registration.
MIN_PASSWORD_LENGTH = 12

# Validated email lowercased so case variants map to the same account.
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


# Body for POST /auth/register. Creates a new user.
class RegisterRequest(RequestBase):
    name: str = Field(description="Full name of the user.")
    email: NormalizedEmail = Field(description="Email address (unique, normalized to lowercase).")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, description="Plain password (will be hashed); minimum 12 characters.")


# Body for POST /auth/login. Authenticates an existing user.
class LoginRequest(RequestBase):
    email: NormalizedEmail = Field(description="User email (normalized to lowercase).")
    password: str = Field(description="Plain password.")


# Response for login and register. Contains JWT and expiry.
class TokenResponse(BaseModel):
    access_token: str = Field(description="Signed JWT for Authorization header.")
    token_type: str = Field(default="bearer", description="Token type (bearer).")
    expires_in: int = Field(description="Token lifetime in seconds.")


# Response for GET /auth/me. Current authenticated user info.
class MeResponse(BaseModel):
    uid: int = Field(description="User id.")
    email: str = Field(description="User email.")
    name: str = Field(description="User display name.")
    plan: UserPlan = Field(description="Plan tier (free or pro).")
