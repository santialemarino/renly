# Data access for feedback.

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.feedback import Feedback
from app.models.user import User
from app.utils.pagination import DEFAULT_PAGE_SIZE, apply_page


# Returns one page of feedback (newest first) paired with the author's email, and the total across
# every page, for the admin review list. Reads across users, so it must run on the privileged session
# (RLS would otherwise hide other rows).
#
# The total counts the same JOIN rather than the table: a feedback row whose author no longer exists is
# not in the list, so counting Feedback alone would page a set the query never returns. The id tiebreak
# makes the order total — several rows can share a created_at.
async def list_all_with_email(session: AsyncSession, *, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> tuple[list[tuple[Feedback, str]], int]:
    joined = select(Feedback, User.email).join(User, User.id == Feedback.user_id)
    count_result = await session.execute(select(func.count()).select_from(joined.subquery()))
    stmt = apply_page(joined.order_by(Feedback.created_at.desc(), Feedback.id.desc()), page, page_size)
    result = await session.execute(stmt)
    return [(feedback, email) for feedback, email in result.all()], count_result.scalar_one()


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
