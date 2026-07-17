from fastapi import APIRouter, Request, Response, status

from app.deps.auth import AdminUser, CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.rate_limit import FEEDBACK_LIMIT, limiter
from app.schemas.feedback import FeedbackAdminResponse, FeedbackCreate, FeedbackResponse
from app.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


# Lists all submitted feedback (newest first) with each author's email. Admin only; reads across
# users on the privileged session.
@router.get("", response_model=list[FeedbackAdminResponse])
async def list_feedback(admin: AdminUser, admin_session: AdminSessionDep) -> list[FeedbackAdminResponse]:
    return await feedback_service.list_feedback(admin_session)


# NOTE: every @limiter.limit endpoint must declare `request: Request` and `response: Response`
# parameters; SlowAPI reads the request from the signature and injects rate-limit headers.


# Submits feedback from the in-app form and notifies every admin by email (best-effort). Stores the
# row on the caller's RLS session; admin_session (privileged) is only used to read the admin emails.
@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(FEEDBACK_LIMIT)
async def create_feedback(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    admin_session: AdminSessionDep,
    data: FeedbackCreate,
) -> FeedbackResponse:
    return await feedback_service.create_feedback(session, admin_session, current_user, data)
