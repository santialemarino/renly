import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback, FeedbackCategory
from app.models.user import User
from app.repositories.feedback_repository import feedback_repository
from app.repositories.user_repository import user_repository
from app.schemas.feedback import FeedbackAdminResponse, FeedbackCreate, FeedbackResponse
from app.services import email_templates, settings_service
from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)


# Lists all feedback (newest first) with each author's email, for the admin review list. Reads
# across users, so it runs on the privileged session.
async def list_feedback(admin_session: AsyncSession) -> list[FeedbackAdminResponse]:
    rows = await feedback_repository.list_all_with_email(admin_session)
    return [
        FeedbackAdminResponse(
            id=feedback.id,
            category=feedback.category,
            message=feedback.message,
            created_at=feedback.created_at,
            email=email,
        )
        for feedback, email in rows
    ]


# Stores a user's feedback, then notifies every admin by email (best-effort, after commit — an email
# outage never fails the submission). admin_session (privileged) is used only to read the admin
# emails, which RLS hides from the submitter's own session.
async def create_feedback(session: AsyncSession, admin_session: AsyncSession, user: User, data: FeedbackCreate) -> FeedbackResponse:
    feedback = Feedback(user_id=user.id, category=data.category, message=data.message)
    feedback = await feedback_repository.create(session, feedback)
    await session.commit()

    await _notify_admins(admin_session, user.email, data.category, data.message)

    return FeedbackResponse.model_validate(feedback)


# Emails every admin about new feedback, each in their own stored language (category label included);
# per-recipient failures are logged and swallowed so one bad send never blocks the others or the
# request. Languages are batch-loaded (one query) to avoid an N+1 over the admin list.
async def _notify_admins(admin_session: AsyncSession, submitter_email: str, category: FeedbackCategory, message: str) -> None:
    admins = await user_repository.list_admins(admin_session)
    if not admins:
        return
    languages = await settings_service.get_languages_by_user_ids(admin_session, [admin.id for admin in admins])
    service = get_email_service()
    messages = [
        email_templates.feedback_notification_email(admin.email, submitter_email, category, message, locale=languages[admin.id]) for admin in admins
    ]
    results = await asyncio.gather(*(service.send(message) for message in messages), return_exceptions=True)
    for admin, result in zip(admins, results):
        if isinstance(result, Exception):
            logger.warning("Failed to send feedback notification to %s.", admin.email, exc_info=result)
