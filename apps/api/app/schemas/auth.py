# Request/response schemas for auth endpoints (HTTP contract).

from pydantic import BaseModel, Field


# Body for POST /auth/register. Creates a new user.
class RegisterRequest(BaseModel):
    name: str = Field(description="Full name of the user.")
    email: str = Field(description="Email address (unique).")
    password: str = Field(description="Plain password (will be hashed).")


# Body for POST /auth/login. Authenticates an existing user.
class LoginRequest(BaseModel):
    email: str = Field(description="User email.")
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
