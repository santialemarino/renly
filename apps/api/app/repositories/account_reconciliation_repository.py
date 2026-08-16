from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account_reconciliation import AccountReconciliation


# List all reconciliations for an account, newest first.
async def list_by_account(session: AsyncSession, account_id: int) -> list[AccountReconciliation]:
    result = await session.execute(
        select(AccountReconciliation)
        .where(AccountReconciliation.account_id == account_id)
        .order_by(AccountReconciliation.as_of_date.desc(), AccountReconciliation.id.desc())
    )
    return list(result.scalars().all())


# Get a single reconciliation by id and account.
async def get_by_id(session: AsyncSession, reconciliation_id: int, account_id: int) -> AccountReconciliation | None:
    result = await session.execute(
        select(AccountReconciliation).where(
            AccountReconciliation.id == reconciliation_id,
            AccountReconciliation.account_id == account_id,
        )
    )
    return result.scalar_one_or_none()


# Latest reconciled date per account, in one grouped query. Returns {account_id: as_of_date}; accounts
# never reconciled are simply absent. Backs the "last reconciled" column without an N+1.
async def get_latest_dates_by_account_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> dict[int, date_type]:
    if not account_ids:
        return {}
    result = await session.execute(
        select(AccountReconciliation.account_id, func.max(AccountReconciliation.as_of_date))
        .where(AccountReconciliation.account_id.in_(account_ids), AccountReconciliation.user_id == user_id)
        .group_by(AccountReconciliation.account_id)
    )
    return {account_id: as_of_date for account_id, as_of_date in result.all()}


# Latest reconciled date per account across ALL users. Deliberately unscoped, for the scheduler only:
# it resolves the reconciled cutoff of many users' funding accounts in one query (the same shape as
# account_repository.get_by_ids_across_users), and its caller has already verified each account's owner.
async def get_latest_dates_across_users(session: AsyncSession, account_ids: list[int]) -> dict[int, date_type]:
    if not account_ids:
        return {}
    result = await session.execute(
        select(AccountReconciliation.account_id, func.max(AccountReconciliation.as_of_date))
        .where(AccountReconciliation.account_id.in_(account_ids))
        .group_by(AccountReconciliation.account_id)
    )
    return {account_id: as_of_date for account_id, as_of_date in result.all()}


# Insert a new reconciliation.
async def create(session: AsyncSession, reconciliation: AccountReconciliation) -> AccountReconciliation:
    session.add(reconciliation)
    await session.flush()
    return reconciliation


# Stage a reconciliation for update (caller commits).
async def save(session: AsyncSession, reconciliation: AccountReconciliation) -> None:
    session.add(reconciliation)


# Delete a reconciliation. Cascades to its adjustment expense or income via the entry-side FK.
async def delete(session: AsyncSession, reconciliation: AccountReconciliation) -> None:
    await session.delete(reconciliation)


# Namespace to call repository functions (e.g. account_reconciliation_repository.list_by_account).
class AccountReconciliationRepository:
    list_by_account = staticmethod(list_by_account)
    get_by_id = staticmethod(get_by_id)
    get_latest_dates_by_account_ids = staticmethod(get_latest_dates_by_account_ids)
    get_latest_dates_across_users = staticmethod(get_latest_dates_across_users)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access account reconciliation persistence.
account_reconciliation_repository = AccountReconciliationRepository()
