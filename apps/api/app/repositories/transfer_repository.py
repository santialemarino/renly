from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlmodel import select

from app.models.account import Account
from app.models.transfer import Transfer


# List a user's transfers, newest first. Optionally narrowed to one account, matching EITHER leg —
# an account's ledger must show money arriving as well as leaving.
async def list_by_user(session: AsyncSession, user_id: int, *, account_id: int | None = None) -> list[Transfer]:
    stmt = select(Transfer).where(Transfer.user_id == user_id)
    if account_id is not None:
        stmt = stmt.where((Transfer.from_account_id == account_id) | (Transfer.to_account_id == account_id))
    result = await session.execute(stmt.order_by(Transfer.date.desc(), Transfer.id.desc()))
    return list(result.scalars().all())


# Get a single transfer by id, scoped to its owner.
async def get_by_id(session: AsyncSession, transfer_id: int, user_id: int) -> Transfer | None:
    result = await session.execute(select(Transfer).where(Transfer.id == transfer_id, Transfer.user_id == user_id))
    return result.scalar_one_or_none()


# Sums one leg of the transfer table per account, for the account-balance union. Bounded BELOW by each
# account's own opening_date via a join rather than a caller-supplied map: opening_balance is by
# definition the balance AT opening_date, so anything earlier is already inside it and would otherwise
# be counted twice. The join keeps that rule in one place and makes it impossible to drift from the
# accounts table. Bounded above by as_of_date when the caller is reconstructing a historical balance.
async def _sum_leg(
    session: AsyncSession,
    leg: InstrumentedAttribute,
    amount: InstrumentedAttribute,
    account_ids: list[int],
    user_id: int,
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = (
        select(leg, func.coalesce(func.sum(amount), 0))
        .join(Account, Account.id == leg)
        .where(leg.in_(account_ids), Transfer.user_id == user_id, Transfer.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(Transfer.date <= as_of_date)
    result = await session.execute(stmt.group_by(leg))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Total transferred OUT of each account (debits the balance).
async def sum_out_by_account_ids(
    session: AsyncSession,
    account_ids: list[int],
    user_id: int,
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    return await _sum_leg(session, Transfer.from_account_id, Transfer.from_amount, account_ids, user_id, as_of_date=as_of_date)


# Total transferred INTO each account (credits the balance). Uses to_amount, which differs from
# from_amount on a cross-currency transfer — each side is counted in its own account's currency.
async def sum_in_by_account_ids(
    session: AsyncSession,
    account_ids: list[int],
    user_id: int,
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    return await _sum_leg(session, Transfer.to_account_id, Transfer.to_amount, account_ids, user_id, as_of_date=as_of_date)


# Whether any transfer references each account on either leg. Drives the currency lock, so a transfer
# counts as a link exactly like an expense or income row does.
async def linked_account_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(Transfer.from_account_id, Transfer.to_account_id).where(
            Transfer.user_id == user_id,
            Transfer.from_account_id.in_(account_ids) | Transfer.to_account_id.in_(account_ids),
        )
    )
    wanted = set(account_ids)
    return {account_id for row in result.all() for account_id in row if account_id in wanted}


# Insert a new transfer.
async def create(session: AsyncSession, transfer: Transfer) -> Transfer:
    session.add(transfer)
    await session.flush()
    return transfer


# Stage a transfer for update (caller commits).
async def save(session: AsyncSession, transfer: Transfer) -> None:
    session.add(transfer)


# Delete a transfer.
async def delete(session: AsyncSession, transfer: Transfer) -> None:
    await session.delete(transfer)


# Namespace to call repository functions (e.g. transfer_repository.list_by_user).
class TransferRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    sum_out_by_account_ids = staticmethod(sum_out_by_account_ids)
    sum_in_by_account_ids = staticmethod(sum_in_by_account_ids)
    linked_account_ids = staticmethod(linked_account_ids)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access transfer persistence.
transfer_repository = TransferRepository()
