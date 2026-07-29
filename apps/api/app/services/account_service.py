from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import AccountCurrencyChangeBlockedError, AccountCurrencyMismatchError, NotFoundError
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


# Returns ({account_id: balance}, {account_ids with any linked money}) for the given accounts,
# derived at query time (one batch query per source): balance = opening_balance + linked income −
# linked expenses − settlements paid from the account. Every linked row is in the account's currency
# (validate_account_link enforces it), so the sums need no per-currency conversion. The linked set is
# free from the same sums (a group is present only when it has rows) and drives the currency lock in
# the response. Transfers are added in a later PR.
async def get_account_summaries(session: AsyncSession, accounts: list[Account], user_id: int) -> tuple[dict[int, Decimal], set[int]]:
    account_ids = [a.id for a in accounts if a.id is not None]
    if not account_ids:
        return {}, set()
    income = await income_repository.sum_by_account_ids(session, account_ids, user_id)
    expenses = await expense_repository.sum_by_account_ids(session, account_ids, user_id)
    settlements = await card_settlement_repository.sum_by_account_ids(session, account_ids, user_id)
    balances = {
        a.id: a.opening_balance + income.get(a.id, ZERO) - expenses.get(a.id, ZERO) - settlements.get(a.id, ZERO)
        for a in accounts
        if a.id is not None
    }
    linked = set(income) | set(expenses) | set(settlements)
    return balances, linked


# Returns {account_id: balance} for the given accounts (see get_account_summaries for the derivation).
async def get_account_balances(session: AsyncSession, accounts: list[Account], user_id: int) -> dict[int, Decimal]:
    balances, _ = await get_account_summaries(session, accounts, user_id)
    return balances


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


# Returns whether any money entry (expense / income / settlement) links this account. Used to lock
# the account's currency once linked, so the derived balance never mixes currencies.
async def account_has_links(session: AsyncSession, account_id: int, user_id: int) -> bool:
    return (
        await expense_repository.exists_by_account_id(session, account_id, user_id)
        or await income_repository.exists_by_account_id(session, account_id, user_id)
        or await card_settlement_repository.exists_by_account_id(session, account_id, user_id)
    )


# Update an existing account. Only provided fields are changed. Changing the currency is blocked once
# money links to the account — it would silently mix currencies in the derived balance (mirrors the
# investment base-currency lock).
async def update_account(
    session: AsyncSession,
    account_id: int,
    user: User,
    **fields: object,
) -> Account:
    account = await get_account(session, account_id, user)
    new_currency = fields.get("currency")
    if new_currency is not None and new_currency != account.currency and await account_has_links(session, account_id, user.id):
        raise AccountCurrencyChangeBlockedError()
    for key, value in fields.items():
        setattr(account, key, value)
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account


# Delete an account. Linked expenses/income/settlements are un-attributed via ON DELETE SET NULL
# (their history is preserved).
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
