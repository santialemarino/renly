# Request schemas for authenticated account self-service (AUTH-8 / AUTH-6).

from pydantic import BaseModel, Field

from app.schemas.auth import MIN_PASSWORD_LENGTH, NAME_MAX_LENGTH, MeResponse, NormalizedEmail, PlainPassword
from app.schemas.base import RequestBase


# Body for POST /me/change-password. Re-verifies the current password before setting a new one.
class ChangePasswordRequest(RequestBase):
    current_password: PlainPassword = Field(description="Current plain password (re-authentication); 72 bytes UTF-8 maximum.")
    new_password: PlainPassword = Field(
        min_length=MIN_PASSWORD_LENGTH, description="New plain password (will be hashed); 12 characters minimum, 72 bytes UTF-8 maximum."
    )


# Body for POST /me/change-email. Re-verifies the password and starts verification of the new address.
class ChangeEmailRequest(RequestBase):
    current_password: PlainPassword = Field(description="Current plain password (re-authentication); 72 bytes UTF-8 maximum.")
    new_email: NormalizedEmail = Field(description="New email address (normalized to lowercase).")


# Body for DELETE /me. Requires the password plus a typed confirmation matching the account email.
class DeleteAccountRequest(RequestBase):
    password: PlainPassword = Field(description="Current plain password (re-authentication); 72 bytes UTF-8 maximum.")
    confirmation: str = Field(description="Must equal the account email to confirm deletion.", max_length=NAME_MAX_LENGTH)


# Body for PATCH /me. The display name, stripped (so a name of spaces alone is refused), and whether the
# user's group seats that still carry the current name follow it.
class UpdateProfileRequest(RequestBase):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH, description="New display name; 1 to 255 characters after trimming.")
    rename_group_seats: bool = Field(
        default=False,
        description="Also rename the user's active group seats still named exactly as the account. Ignored when the name is unchanged.",
    )


# Response for PATCH /me: the user as GET /auth/me returns them, plus how many group seats were renamed.
class UpdateProfileResponse(MeResponse):
    group_seats_renamed: int = Field(description="How many of the user's group seats took the new name; 0 unless rename_group_seats was set.")


# One group where the user's seat still carries their account name.
class GroupUsingAccountNameResponse(BaseModel):
    id: int = Field(description="Group id.")
    name: str = Field(description="Group name.")

    model_config = {"from_attributes": True}


# Response for GET /me/name/groups: the groups a rename with rename_group_seats would reach, by group name.
class GroupsUsingAccountNameResponse(BaseModel):
    groups: list[GroupUsingAccountNameResponse] = Field(description="Groups where the user's active seat is still named exactly as their account.")

    model_config = {"from_attributes": True}
