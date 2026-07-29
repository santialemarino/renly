# Request schemas for authenticated account self-service (AUTH-8 / AUTH-6).

from pydantic import Field

from app.schemas.auth import MIN_PASSWORD_LENGTH, NormalizedEmail
from app.schemas.base import RequestBase


# Body for POST /me/change-password. Re-verifies the current password before setting a new one.
class ChangePasswordRequest(RequestBase):
    current_password: str = Field(description="Current plain password (re-authentication).")
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, description="New plain password (will be hashed); minimum 12 characters.")


# Body for POST /me/change-email. Re-verifies the password and starts verification of the new address.
class ChangeEmailRequest(RequestBase):
    current_password: str = Field(description="Current plain password (re-authentication).")
    new_email: NormalizedEmail = Field(description="New email address (normalized to lowercase).")


# Body for DELETE /me. Requires the password plus a typed confirmation matching the account email.
class DeleteAccountRequest(RequestBase):
    password: str = Field(description="Current plain password (re-authentication).")
    confirmation: str = Field(description="Must equal the account email to confirm deletion.")
