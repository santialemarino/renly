# Data access for users.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User


# Fetches user by email from the database. Lowercases the input so lookups are case-insensitive.
async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


# Persists a new user and flushes to get the id.
async def create(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


# Persists changes to an existing user.
async def save(session: AsyncSession, user: User) -> None:
    session.add(user)


# Namespace to call repository functions (e.g. user_repository.get_by_email).
class UserRepository:
    create = staticmethod(create)
    get_by_email = staticmethod(get_by_email)
    save = staticmethod(save)


# Singleton used by services to access user persistence.
user_repository = UserRepository()
