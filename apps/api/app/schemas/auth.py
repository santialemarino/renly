# Request/response schemas for auth endpoints (HTTP contract).

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.config import SignupMode
from app.models.auth_token import AuthTokenType
from app.models.user import UserPlan
from app.schemas.base import RequestBase
from app.schemas.settings import SUPPORTED_LANGUAGES

# Minimum password length enforced at registration.
MIN_PASSWORD_LENGTH = 12

# Validated email lowercased so case variants map to the same account.
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


# Coerces an unsupported (or empty) language to None so a stray value never 422s signup — the
# service falls back to the default email locale.
def _supported_language_or_none(value: str | None) -> str | None:
    return value if value in SUPPORTED_LANGUAGES else None


# Optional supported UI language ('en' | 'es'); anything else becomes None.
SupportedLanguage = Annotated[str | None, AfterValidator(_supported_language_or_none)]


# Body for POST /auth/register. Creates a new user.
class RegisterRequest(RequestBase):
    name: str = Field(description="Full name of the user.")
    email: NormalizedEmail = Field(description="Email address (unique, normalized to lowercase).")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, description="Plain password (will be hashed); minimum 12 characters.")
    invite_token: str | None = Field(default=None, description="Raw invite token from the emailed link; required in invite-only mode (SIGNUP_MODE).")
    language: SupportedLanguage = Field(
        default=None,
        description=(
            "Active UI locale ('en' | 'es') from the web; seeds the new user's language preference "
            "and localizes the verification email. Unsupported values are ignored."
        ),
    )


# Body for POST /auth/login. Authenticates an existing user.
class LoginRequest(RequestBase):
    email: NormalizedEmail = Field(description="User email (normalized to lowercase).")
    password: str = Field(description="Plain password.")
    remember_me: bool = Field(default=False, description="When true, the refresh token gets the long 'remember me' window so the session persists.")


# Body for POST /auth/refresh. Exchanges a refresh token for a new access token (AUTH-7).
class RefreshRequest(RequestBase):
    refresh_token: str = Field(description="The refresh token returned by login or a prior refresh.")


# Response for login and refresh. Carries the access token plus the rotating refresh token (AUTH-7).
class TokenResponse(BaseModel):
    access_token: str = Field(description="Signed JWT for Authorization header.")
    token_type: str = Field(default="bearer", description="Token type (bearer).")
    expires_in: int = Field(description="Access token lifetime in seconds.")
    refresh_token: str = Field(description="Opaque refresh token; exchange at POST /auth/refresh for a new access token.")
    refresh_expires_in: int = Field(description="Refresh token lifetime in seconds.")


# Response for GET /auth/me. Current authenticated user info.
class MeResponse(BaseModel):
    uid: int = Field(description="User id.")
    email: str = Field(description="User email.")
    name: str = Field(description="User display name.")
    plan: UserPlan = Field(description="Plan tier (free or pro).")
    email_verified: bool = Field(description="Whether the email address has been verified.")
    is_admin: bool = Field(description="Whether the user is an admin (gates the admin invite surface).")


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


# Response for GET /auth/signup-context. Tells the web whether signup is invite-only and, for a valid
# invite token, the address to lock the form to (null when open, or the token is missing/invalid).
class SignupContextResponse(BaseModel):
    signup_mode: SignupMode = Field(description="Registration access mode (invite or open).")
    invited_email: str | None = Field(
        default=None, description="Email the invite is bound to (lock the form to it); null when open or the token is invalid."
    )
