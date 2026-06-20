# Request/response schemas for auth endpoints (HTTP contract).

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.models.auth_token import AuthTokenType
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
    email_verified: bool = Field(description="Whether the email address has been verified.")


# Body for POST /auth/verify-email/request and POST /auth/forgot-password. Identifies the address to
# (re)send a verification or reset email to; the response is uniform whether or not it has an account.
class EmailActionRequest(RequestBase):
    email: NormalizedEmail = Field(description="Email address to act on (normalized to lowercase).")


# Body for POST /auth/verify-email/confirm. Confirms an email-verification or email-change token.
class ConfirmEmailRequest(RequestBase):
    token: str = Field(description="Raw token from the emailed verification link.")


# Body for POST /auth/reset-password. Sets a new password from a reset token.
class ResetPasswordRequest(RequestBase):
    token: str = Field(description="Raw token from the emailed reset link.")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, description="New plain password (will be hashed); minimum 12 characters.")


# Uniform response for register / verify-request / forgot-password / change-email. Carries no
# account-existence signal — only a generic acknowledgement message.
class MessageResponse(BaseModel):
    detail: str = Field(description="Generic acknowledgement message.")


# Response for POST /auth/verify-email/confirm. token_type lets the web tailor its confirmation copy
# (a fresh verification vs an email change).
class ConfirmEmailResponse(BaseModel):
    detail: str = Field(description="Human-readable confirmation message.")
    token_type: AuthTokenType = Field(description="Which flow the token completed (email_verification or email_change).")
