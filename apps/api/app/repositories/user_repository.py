# Data access for users.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User


# Returns the emails of all admin users, for admin notifications (e.g. new feedback). Runs on the
# privileged session — under RLS a non-admin can't read other users' rows.
async def list_admin_emails(session: AsyncSession) -> list[str]:
    result = await session.execute(select(User.email).where(User.is_admin))
    return list(result.scalars().all())


# Fetches user by id from the database. Returns None when no user matches.
async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


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


# Deletes a user; FK ON DELETE CASCADE removes all the user's owned rows (AUTH-6).
async def delete(session: AsyncSession, user: User) -> None:
    await session.delete(user)


# Namespace to call repository functions (e.g. user_repository.get_by_email).
class UserRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_email = staticmethod(get_by_email)
    get_by_id = staticmethod(get_by_id)
    list_admin_emails = staticmethod(list_admin_emails)
    save = staticmethod(save)


# Singleton used by services to access user persistence.
user_repository = UserRepository()
