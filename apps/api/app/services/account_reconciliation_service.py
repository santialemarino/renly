# Account reconciliation business logic (Bucket 3 #1 — Option F, point-in-time).
# Implements:
#   - compute_account_balance_at(): the account's derived balance as of a date (the cash sibling of
#     card_reconciliation_service.compute_bucket_balance_at).
#   - create_reconciliation(): records the real balance the user read and posts the single adjustment
#     entry that closes the gap, so the balance is true from that date forward.
#
# Reconciliation is the keystone of the "approximate cash" model: linking every movement is optional,
# so the derived balance drifts. Entering the real balance snaps it back with one dated true-up
# instead of demanding the user back-fill history. It is also the universal fee/tax catch-all —
# bank fees, interest, FX spread, and perceptions all land in the difference with no per-fee modelling.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountReconciliationBeforeLastError,
    AccountReconciliationBeforeOpeningError,
    AccountReconciliationFutureDateError,
    AccountReconciliationNotLatestError,
    NotFoundError,
)
from app.models.account import Account
from app.models.account_reconciliation import AccountReconciliation
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
from app.repositories import (
    account_reconciliation_repository,
    card_settlement_repository,
    expense_repository,
    income_repository,
    pot_ownership_repository,
    transfer_repository,
)
from app.services import account_service, settings_service

ZERO = Decimal(0)


# --- Pure helpers ---


# Pure computation: the adjustment the account needs to match reality. Positive means the account
# really holds more than Renly computed (post an income); negative means less (post an expense).
def compute_reconciliation_difference(statement_balance: Decimal, computed_balance: Decimal) -> Decimal:
    return statement_balance - computed_balance


# --- Balance ---


# Derived balance of an account at as_of_date: opening_balance (only once the account has opened)
# plus linked income, minus linked expenses and settlements drawn from it, all dated on or before
# as_of_date, plus both transfer legs. Mirrors account_service.get_account_balances but bounded in time.
async def compute_account_balance_at(
    session: AsyncSession,
    account: Account,
    as_of_date: date_type,
) -> Decimal:
    if account.id is None:
        return ZERO
    account_ids = [account.id]
    income = await income_repository.sum_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    expenses = await expense_repository.sum_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    settlements = await card_settlement_repository.sum_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    transfers_in = await transfer_repository.sum_in_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    transfers_out = await transfer_repository.sum_out_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    ownership_in = await pot_ownership_repository.sum_in_by_account_ids(session, account_ids, as_of_date=as_of_date)
    ownership_out = await pot_ownership_repository.sum_out_by_account_ids(session, account_ids, as_of_date=as_of_date)
    opening = account.opening_balance if account.opening_date <= as_of_date else ZERO
    return (
        opening
        + income.get(account.id, ZERO)
        - expenses.get(account.id, ZERO)
        - settlements.get(account.id, ZERO)
        + transfers_in.get(account.id, ZERO)
        - transfers_out.get(account.id, ZERO)
        + ownership_in.get(account.id, ZERO)
        - ownership_out.get(account.id, ZERO)
    )


# --- Reconciliation CRUD ---


# Latest reconciled date per account, in one grouped query. Returns {account_id: as_of_date}; accounts
# never reconciled are absent. Surfaces "last reconciled" on the accounts list without an N+1.
async def get_latest_reconciled_dates(session: AsyncSession, accounts: list[Account], user_id: int) -> dict[int, date_type]:
    account_ids = [a.id for a in accounts if a.id is not None]
    return await account_reconciliation_repository.get_latest_dates_by_account_ids(session, account_ids, user_id)


# Latest reconciled date for one account, or None when it has never been reconciled. Reuses the
# batch query with a single id, the same way compute_account_balance_at reuses the batch sums.
async def get_latest_reconciled_date(session: AsyncSession, account_id: int, user_id: int) -> date_type | None:
    latest = await account_reconciliation_repository.get_latest_dates_by_account_ids(session, [account_id], user_id)
    return latest.get(account_id)


# List an account's reconciliations, newest first (verifies account ownership).
async def list_reconciliations(session: AsyncSession, account_id: int, user: User) -> list[AccountReconciliation]:
    await account_service.get_account(session, account_id, user)
    return await account_reconciliation_repository.list_by_account(session, account_id)


# Get a single reconciliation by id (verifies account ownership).
async def get_reconciliation(
    session: AsyncSession,
    account_id: int,
    reconciliation_id: int,
    user: User,
) -> AccountReconciliation:
    await account_service.get_account(session, account_id, user)
    reconciliation = await account_reconciliation_repository.get_by_id(session, reconciliation_id, account_id)
    if reconciliation is None:
        raise NotFoundError("Reconciliation not found.")
    return reconciliation


# Record a point-in-time true-up of an account against its real balance. Atomic:
#   1. Compute the derived balance at as_of_date.
#   2. Compute the difference; write the reconciliation row.
#   3. Create the matching adjustment entry (dated on as_of_date, linked to the account so it enters
#      the running balance, tagged source='reconciliation' and category account_adjustment so true-ups
#      are identifiable and separable from real spending) when the difference is non-zero, and patch
#      the back-pointer. NOTE: the category labels the row, it does not exclude it — adjustments still
#      count toward income/expense totals and the category breakdown, exactly like the card
#      reconciliation categories. That is deliberate: money the reconciliation accounts for really did
#      move, it just was not itemised.
# Unlike card reconciliation there is no replace step: a later reconciliation of the same account
# simply appends. Re-running the same date is self-correcting — the earlier adjustment is already in
# the computed balance, so the new difference is zero and no second adjustment is posted. That only
# holds forward, which is why an out-of-order (older) date is rejected: its adjustment would land
# underneath the newer reconciliation, whose date bound cannot see it, skewing the newer balance.
async def create_reconciliation(
    session: AsyncSession,
    account_id: int,
    user: User,
    *,
    as_of_date: date_type,
    statement_balance: Decimal,
) -> AccountReconciliation:
    account = await account_service.get_account(session, account_id, user)
    today = await settings_service.get_user_today(session, user.id)
    if as_of_date > today:
        raise AccountReconciliationFutureDateError()
    if as_of_date < account.opening_date:
        raise AccountReconciliationBeforeOpeningError(account.opening_date)
    last_reconciled = await get_latest_reconciled_date(session, account_id, user.id)
    if last_reconciled is not None and as_of_date < last_reconciled:
        raise AccountReconciliationBeforeLastError(last_reconciled)

    computed = await compute_account_balance_at(session, account, as_of_date)
    difference = compute_reconciliation_difference(statement_balance, computed)

    reconciliation = AccountReconciliation(
        user_id=user.id,
        account_id=account_id,
        as_of_date=as_of_date,
        statement_balance=statement_balance,
        computed_balance=computed,
        difference=difference,
    )
    reconciliation = await account_reconciliation_repository.create(session, reconciliation)

    if difference > 0:
        adjustment_income = IncomeEntry(
            user_id=user.id,
            date=as_of_date,
            amount=difference,
            currency=account.currency,
            category=IncomeCategory.account_adjustment,
            account_id=account_id,
            source="reconciliation",
            account_reconciliation_id=reconciliation.id,
        )
        adjustment_income = await income_repository.create(session, adjustment_income)
        reconciliation.adjustment_income_id = adjustment_income.id
        await account_reconciliation_repository.save(session, reconciliation)
    elif difference < 0:
        # payment_method stays NULL: a true-up is not a payment, and a card method would collide with
        # the account link (a card expense never draws an account directly).
        adjustment_expense = ExpenseEntry(
            user_id=user.id,
            date=as_of_date,
            amount=-difference,
            currency=account.currency,
            category=ExpenseCategory.account_adjustment,
            account_id=account_id,
            source="reconciliation",
            account_reconciliation_id=reconciliation.id,
        )
        adjustment_expense = await expense_repository.create(session, adjustment_expense)
        reconciliation.adjustment_expense_id = adjustment_expense.id
        await account_reconciliation_repository.save(session, reconciliation)

    await session.commit()
    await session.refresh(reconciliation)
    return reconciliation


# Delete a reconciliation. Its adjustment entry is cascade-dropped via
# expense_entries / income_entries.account_reconciliation_id, so the balance returns to what it was
# before the true-up — the escape hatch for a mistyped balance. Only the account's most recent
# reconciliation can be deleted: an older one's adjustment is already inside every later
# reconciliation's recorded computed_balance, so removing it would silently skew those.
async def delete_reconciliation(
    session: AsyncSession,
    account_id: int,
    reconciliation_id: int,
    user: User,
) -> None:
    reconciliation = await get_reconciliation(session, account_id, reconciliation_id, user)
    last_reconciled = await get_latest_reconciled_date(session, account_id, user.id)
    if last_reconciled is not None and reconciliation.as_of_date < last_reconciled:
        raise AccountReconciliationNotLatestError(last_reconciled)
    await account_reconciliation_repository.delete(session, reconciliation)
    await session.commit()
