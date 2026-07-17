# Data access for feedback.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.feedback import Feedback
from app.models.user import User


# Returns all feedback (newest first) paired with the author's email, for the admin review list.
# Reads across users, so it must run on the privileged session (RLS would otherwise hide other rows).
async def list_all_with_email(session: AsyncSession) -> list[tuple[Feedback, str]]:
    result = await session.execute(select(Feedback, User.email).join(User, User.id == Feedback.user_id).order_by(Feedback.created_at.desc()))
    return [(feedback, email) for feedback, email in result.all()]


# Persists a new feedback row and flushes to get the id (the service commits).
async def create(session: AsyncSession, feedback: Feedback) -> Feedback:
    session.add(feedback)
    await session.flush()
    return feedback


# Namespace to call repository functions (e.g. feedback_repository.create).
class FeedbackRepository:
    create = staticmethod(create)
    list_all_with_email = staticmethod(list_all_with_email)


# Singleton used by services to access feedback persistence.
feedback_repository = FeedbackRepository()
