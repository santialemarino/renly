from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.repositories.utils import apply_listing_filters

_SORT_COLUMNS = {
    "name": Account.name,
    "type": Account.type,
    "currency": Account.currency,
    "opening_date": Account.opening_date,
}


# List accounts for a user with optional search, sorting, and archive filtering.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Account]:
    stmt = apply_listing_filters(
        select(Account),
        Account,
        user_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
        include_ids=None,
        sort_columns=_SORT_COLUMNS,
        default_order=Account.name,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single account by id and user_id.
async def get_by_id(session: AsyncSession, account_id: int, user_id: int) -> Account | None:
    result = await session.execute(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    return result.scalar_one_or_none()


# Get multiple accounts by id for a user (batch sibling of get_by_id).
async def get_by_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> list[Account]:
    if not account_ids:
        return []
    result = await session.execute(select(Account).where(Account.id.in_(account_ids), Account.user_id == user_id))
    return list(result.scalars().all())


# Get multiple accounts by id across ALL users. Deliberately unscoped, for the scheduler only: it
# resolves the default funding accounts of many users' plans in one query (the same shape as
# subscription_repository.list_active_due), and its caller re-checks each row's owner (SEC-4).
async def get_by_ids_across_users(session: AsyncSession, account_ids: list[int]) -> list[Account]:
    if not account_ids:
        return []
    result = await session.execute(select(Account).where(Account.id.in_(account_ids)))
    return list(result.scalars().all())


# Returns whether the user has any account (cheap existence check for the onboarding checklist;
# counts archived accounts too, so archiving a lone account doesn't un-complete the step).
async def exists_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Account.id).where(Account.user_id == user_id).limit(1))
    return result.first() is not None


# Insert a new account.
async def create(session: AsyncSession, account: Account) -> Account:
    session.add(account)
    await session.flush()
    return account


# Stage an account for update (caller commits).
async def save(session: AsyncSession, account: Account) -> None:
    session.add(account)


# Delete an account.
async def delete(session: AsyncSession, account: Account) -> None:
    await session.delete(account)


# Namespace to call repository functions (e.g. account_repository.list_by_user).
class AccountRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    get_by_ids = staticmethod(get_by_ids)
    get_by_ids_across_users = staticmethod(get_by_ids_across_users)
    exists_by_user = staticmethod(exists_by_user)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access account persistence.
account_repository = AccountRepository()
