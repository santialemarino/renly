from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.investment import Investment


# Lists investments for a user, optionally and defaulted to only active. Returns list ordered by id.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    active_only: bool = True,
) -> list[Investment]:
    stmt = select(Investment).where(Investment.user_id == user_id)
    if active_only:
        stmt = stmt.where(Investment.is_active.is_(True))
    stmt = stmt.order_by(Investment.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Fetches a single investment by id and user_id. Returns None if not found or not owned.
async def get_by_id(
    session: AsyncSession,
    investment_id: int,
    user_id: int,
) -> Investment | None:
    result = await session.execute(
        select(Investment).where(
            Investment.id == investment_id,
            Investment.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


# Persists investment, commits, refreshes, and returns it (with id set).
async def create(session: AsyncSession, investment: Investment) -> Investment:
    session.add(investment)
    await session.commit()
    await session.refresh(investment)
    return investment


# Persists changes to an existing investment.
async def save(session: AsyncSession, investment: Investment) -> None:
    session.add(investment)
    await session.commit()


# Namespace to call repository functions (e.g. investment_repository.list_by_user).
class InvestmentRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)


# Singleton used by services to access investment persistence.
investment_repository = InvestmentRepository()
