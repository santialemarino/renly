from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import AccountCurrencyMismatchError, NotFoundError
from app.models.account import Account, AccountType
from app.models.user import User
from app.repositories import (
    account_repository,
    card_settlement_repository,
    expense_repository,
    income_repository,
)

ZERO = Decimal(0)


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


# Validates that an account link (from an expense / income / settlement) is legal: the account must
# exist and belong to the user (SEC-4), and its currency must match the entry's — a cash balance
# stays exact, so mismatched-currency links are rejected (mirrors the investment base-currency lock).
# A None account_id is a no-op (unlinked entries are allowed and untouched).
async def validate_account_link(session: AsyncSession, user: User, account_id: int | None, currency: str) -> None:
    if account_id is None:
        return
    account = await account_repository.get_by_id(session, account_id, user.id)
    if account is None:
        raise NotFoundError("Account not found.")
    if account.currency != currency:
        raise AccountCurrencyMismatchError(currency, account.currency)


# Returns {account_id: balance} for the given accounts, derived at query time:
# opening_balance + linked income − linked expenses − settlements paid from the account.
# Every linked row is in the account's currency (validate_account_link enforces it), so the sums
# need no per-currency conversion. Transfers are added in a later PR. One batch query per source.
async def get_account_balances(session: AsyncSession, accounts: list[Account], user_id: int) -> dict[int, Decimal]:
    account_ids = [a.id for a in accounts if a.id is not None]
    if not account_ids:
        return {}
    income = await income_repository.sum_by_account_ids(session, account_ids, user_id)
    expenses = await expense_repository.sum_by_account_ids(session, account_ids, user_id)
    settlements = await card_settlement_repository.sum_by_account_ids(session, account_ids, user_id)
    return {
        a.id: a.opening_balance + income.get(a.id, ZERO) - expenses.get(a.id, ZERO) - settlements.get(a.id, ZERO)
        for a in accounts
        if a.id is not None
    }


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
