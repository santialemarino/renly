from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User


# Fetches user by email from the database.
async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# Persists user, commits, refreshes, and returns it (with id set).
async def create(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# Persists changes to an existing user (add + commit).
async def save(session: AsyncSession, user: User) -> None:
    session.add(user)
    await session.commit()


# Namespace to call repository functions (e.g. user_repository.get_by_email).
class UserRepository:
    get_by_email = staticmethod(get_by_email)
    create = staticmethod(create)
    save = staticmethod(save)


# Singleton used by services to access user persistence.
user_repository = UserRepository()
