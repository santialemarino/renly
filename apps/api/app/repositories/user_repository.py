# Data access for users.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User
from app.repositories.utils import chunked


# Returns all admin users, for admin notifications (e.g. new feedback) that need each admin's id
# (to resolve their language) plus their email. Runs on the privileged session — under RLS a
# non-admin can't read other users' rows.
async def list_admins(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).where(User.is_admin))
    return list(result.scalars().all())


# Fetches user by id from the database. Returns None when no user matches.
async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


# Batch variant of get_by_id: every requested user in one query, keyed by id. The notification fan-out
# needs each recipient's email address at once, so the single-id version inside that loop would be a
# query per recipient. Runs on the privileged session — under RLS a user can only read their own row.
async def get_by_ids(session: AsyncSession, user_ids: list[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    users: dict[int, User] = {}
    for chunk in chunked(user_ids):
        result = await session.execute(select(User).where(User.id.in_(chunk)))
        users.update({user.id: user for user in result.scalars().all()})
    return users


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


# Takes a row lock on the user for the rest of the transaction and re-reads the row into the copy the
# session already holds. The caller's copy was loaded when the request authenticated, before any lock,
# so a rename that committed since would otherwise be invisible to it.
#
# FOR NO KEY UPDATE (`key_share=True`), the lock a name change takes anyway: a row that merely
# references the user (an audit entry naming its actor) goes in without waiting for it. Account
# deletion's FOR UPDATE still waits, and the seats come before this lock on every path that takes both
# (see group_repository, "The row-lock order").
async def lock(session: AsyncSession, user_id: int) -> None:
    await session.execute(select(User).where(User.id == user_id).with_for_update(key_share=True).execution_options(populate_existing=True))


# Namespace to call repository functions (e.g. user_repository.get_by_email).
class UserRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_email = staticmethod(get_by_email)
    get_by_id = staticmethod(get_by_id)
    get_by_ids = staticmethod(get_by_ids)
    list_admins = staticmethod(list_admins)
    lock = staticmethod(lock)
    save = staticmethod(save)


# Singleton used by services to access user persistence.
user_repository = UserRepository()
