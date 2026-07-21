from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.rate_limit import CHANGE_EMAIL_LIMIT, limiter
from app.schemas.auth import MessageResponse
from app.schemas.user_account import ChangeEmailRequest, ChangePasswordRequest, DeleteAccountRequest
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
# password hash and api-key secrets.
@router.get("/export")
async def export_data(current_user: CurrentUser, session: SessionDep, response: Response) -> dict[str, Any]:
    data = await user_account_service.export_user_data(session, current_user)
    response.headers["Content-Disposition"] = 'attachment; filename="renly-export.json"'
    return data


# Permanently deletes the current user's account after re-verifying the password and a typed email
# confirmation (AUTH-6). FK ON DELETE CASCADE removes every owned row; the invite that created the
# account is cleared on the privileged session (RLS hides it from the user's own session).
@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(body: DeleteAccountRequest, current_user: CurrentUser, session: SessionDep, admin_session: AdminSessionDep) -> None:
    await user_account_service.delete_account(session, admin_session, current_user, body.password, body.confirmation)
