from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.rate_limit import CHANGE_EMAIL_LIMIT, CHANGE_NAME_LIMIT, EXPORT_LIMIT, limiter
from app.schemas.auth import MessageResponse
from app.schemas.user_account import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    GroupsUsingAccountNameResponse,
    GroupUsingAccountNameResponse,
    UpdateProfileRequest,
    UpdateProfileResponse,
)
from app.services import user_account_service

router = APIRouter(prefix="/me", tags=["account"])


# Changes the current user's password after re-verifying the current one; kills other sessions.
# Returns 401 on a wrong current password, 400 if the new password is breached (AUTH-8).
@router.post("/change-password", response_model=MessageResponse)
async def change_password(body: ChangePasswordRequest, current_user: CurrentUser, session: SessionDep) -> MessageResponse:
    await user_account_service.change_password(session, current_user, body.current_password, body.new_password)
    return MessageResponse(detail="Your password has been changed.")


# Starts an email change after re-verifying the password; emails a confirmation link to the new
# address (the switch happens on confirm). Uniform 202 — never reveals if the target is taken
# (AUTH-8). Runs the change on the privileged session so the availability check sees every account.
@router.post("/change-email", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(CHANGE_EMAIL_LIMIT)
async def change_email(
    request: Request,
    response: Response,
    body: ChangeEmailRequest,
    current_user: CurrentUser,
    admin_session: AdminSessionDep,
) -> MessageResponse:
    await user_account_service.change_email(admin_session, current_user, body.current_password, body.new_email)
    return MessageResponse(detail="If that address is available, we've sent it a confirmation link.")


# Exports the current user's full data set as a downloadable JSON document (AUTH-6). Excludes the
# password hash and api-key secrets. Unpaged by contract (it is the whole data set), so its cost grows with
# the account and it is rate-limited per user instead.
@router.get("/export")
@limiter.limit(EXPORT_LIMIT)
async def export_data(request: Request, response: Response, current_user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    data = await user_account_service.export_user_data(session, current_user)
    response.headers["Content-Disposition"] = 'attachment; filename="renly-export.json"'
    return data


# Lists the groups where the user's seat is still named exactly as their account: the ones renaming the
# account with rename_group_seats would reach. On the request session — the user's own seats, in groups
# the membership policy already shows them.
@router.get("/name/groups", response_model=GroupsUsingAccountNameResponse)
async def list_groups_using_account_name(current_user: CurrentUser, session: SessionDep) -> GroupsUsingAccountNameResponse:
    groups = await user_account_service.list_groups_using_account_name(session, current_user)
    return GroupsUsingAccountNameResponse(groups=[GroupUsingAccountNameResponse.model_validate(group) for group in groups])


# Updates the current user's profile: the display name, and optionally the group seats still carrying
# the old one. Returns the user as GET /auth/me does, plus the number of seats renamed. Rate-limited per
# user (CHANGE_NAME_LIMIT). On the request session: the seats renamed are the caller's own, in groups
# they are an active member of, which is exactly what the membership policy lets them write.
@router.patch("", response_model=UpdateProfileResponse)
@limiter.limit(CHANGE_NAME_LIMIT)
async def update_profile(
    request: Request, response: Response, body: UpdateProfileRequest, current_user: CurrentUser, session: SessionDep
) -> UpdateProfileResponse:
    user, seats_renamed = await user_account_service.update_profile(session, current_user, body.name, rename_group_seats=body.rename_group_seats)
    return UpdateProfileResponse(
        uid=user.id,
        email=user.email,
        name=user.name,
        plan=user.plan,
        email_verified=user.email_verified_at is not None,
        is_admin=user.is_admin,
        group_seats_renamed=seats_renamed,
    )


# Permanently deletes the current user's account after re-verifying the password and a typed email
# confirmation (AUTH-6). FK ON DELETE CASCADE removes every owned row; the invite that created the
# account is cleared on the privileged session (RLS hides it from the user's own session).
@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(body: DeleteAccountRequest, current_user: CurrentUser, session: SessionDep, admin_session: AdminSessionDep) -> None:
    await user_account_service.delete_account(session, admin_session, current_user, body.password, body.confirmation)
