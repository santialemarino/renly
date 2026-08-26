from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlmodel import select

from app.models.account import Account
from app.models.transfer import Transfer
from app.repositories.utils import account_scope_matches


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


# Whether any transfer references this account on either leg (used to lock the account's currency once
# linked). Deliberately NOT bounded by opening_date, unlike the balance sums: a pre-opening transfer
# contributes nothing to the balance, but its amounts are still denominated in this account's currency,
# and reinterpreting them under a new one is exactly what the lock exists to prevent.
async def exists_by_account_id(session: AsyncSession, account_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(Transfer.id)
        .where(
            Transfer.user_id == user_id,
            (Transfer.from_account_id == account_id) | (Transfer.to_account_id == account_id),
        )
        .limit(1)
    )
    return result.first() is not None


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
        .where(leg.in_(account_ids), account_scope_matches(Transfer, user_id), Transfer.date >= Account.opening_date)
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


# Monthly totals for one leg, grouped by (account_id, year, month), for the net-worth evolution chart's
# cash series. Carries the same opening_date lower bound as the point-in-time sums, so the chart and the
# headline balance agree. Returns a list of (account_id, year, month, total).
async def _sum_leg_monthly(
    session: AsyncSession,
    leg: InstrumentedAttribute,
    amount: InstrumentedAttribute,
    account_ids: list[int],
    user_id: int,
) -> list[tuple[int, int, int, Decimal]]:
    if not account_ids:
        return []
    year_col = func.extract("year", Transfer.date).label("year")
    month_col = func.extract("month", Transfer.date).label("month")
    result = await session.execute(
        select(leg, year_col, month_col, func.coalesce(func.sum(amount), 0))
        .join(Account, Account.id == leg)
        .where(leg.in_(account_ids), account_scope_matches(Transfer, user_id), Transfer.date >= Account.opening_date)
        .group_by(leg, year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), Decimal(str(row[3]))) for row in result.all()]


# Monthly totals transferred OUT of each account.
async def sum_out_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    return await _sum_leg_monthly(session, Transfer.from_account_id, Transfer.from_amount, account_ids, user_id)


# Monthly totals transferred INTO each account.
async def sum_in_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    return await _sum_leg_monthly(session, Transfer.to_account_id, Transfer.to_amount, account_ids, user_id)


# Which of the given accounts any transfer references, on either leg. Same unbounded semantics as its
# peers — see exists_by_account_id.
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


# Namespace to call repository functions (e.g. transfer_repository.list_by_user).
class TransferRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    exists_by_account_id = staticmethod(exists_by_account_id)
    linked_account_ids = staticmethod(linked_account_ids)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    sum_out_by_account_ids = staticmethod(sum_out_by_account_ids)
    sum_in_by_account_ids = staticmethod(sum_in_by_account_ids)
    sum_out_by_account_ids_monthly = staticmethod(sum_out_by_account_ids_monthly)
    sum_in_by_account_ids_monthly = staticmethod(sum_in_by_account_ids_monthly)


# Singleton used by services to access transfer persistence.
transfer_repository = TransferRepository()
