from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.account import Account, AccountType
from app.models.user import User
from app.repositories import account_repository


# List accounts for a user with optional search, sorting, and archive filtering.
async def list_accounts(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Account]:
    return await account_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single account by id. Raises NotFoundError if not found.
async def get_account(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await account_repository.get_by_id(session, account_id, user.id)
    if account is None:
        raise NotFoundError("Account not found.")
    return account


# Returns {account_id: balance} for the given accounts. In this PR the balance is just the
# opening_balance; PR 2 (money-linking) extends this to add linked income minus linked
# expenses/settlements plus/minus transfers, computed at query time.
async def get_account_balances(accounts: list[Account]) -> dict[int, Decimal]:
    return {a.id: a.opening_balance for a in accounts if a.id is not None}


# Create a new account.
async def create_account(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    type: AccountType,
    currency: str,
    opening_balance: Decimal,
    opening_date: date_type,
    notes: str | None = None,
) -> Account:
    account = Account(
        user_id=user.id,
        name=name,
        type=type,
        currency=currency,
        opening_balance=opening_balance,
        opening_date=opening_date,
        notes=notes,
    )
    account = await account_repository.create(session, account)
    await session.commit()
    return account


# Update an existing account. Only provided fields are changed.
async def update_account(
    session: AsyncSession,
    account_id: int,
    user: User,
    **fields: object,
) -> Account:
    account = await get_account(session, account_id, user)
    for key, value in fields.items():
        setattr(account, key, value)
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account


# Delete an account. Linked expenses/income/settlements are un-attributed via ON DELETE SET NULL
# (their history is preserved); no linked rows exist yet in this PR.
async def delete_account(session: AsyncSession, account_id: int, user: User) -> None:
    account = await get_account(session, account_id, user)
    await account_repository.delete(session, account)
    await session.commit()


# Archive an account (set is_active = false).
async def archive_account(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await get_account(session, account_id, user)
    account.is_active = False
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account


# Unarchive an account (set is_active = true).
async def unarchive_account(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await get_account(session, account_id, user)
    account.is_active = True
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account
