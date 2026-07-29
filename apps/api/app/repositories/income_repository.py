from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.income_entry import IncomeCategory, IncomeEntry


# List income entries for a user with optional filters and pagination.
async def list_by_user_filtered(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    category: IncomeCategory | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[IncomeEntry], int]:
    base = select(IncomeEntry).where(IncomeEntry.user_id == user_id)

    if search:
        base = base.where(IncomeEntry.notes.ilike(f"%{search}%"))
    if category is not None:
        base = base.where(IncomeEntry.category == category)
    if date_from is not None:
        base = base.where(IncomeEntry.date >= date_from)
    if date_to is not None:
        base = base.where(IncomeEntry.date <= date_to)

    count_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    query = base.order_by(IncomeEntry.date.desc(), IncomeEntry.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    return list(result.scalars().all()), total


# Get a single income entry by id and user_id.
async def get_by_id(session: AsyncSession, income_id: int, user_id: int) -> IncomeEntry | None:
    result = await session.execute(select(IncomeEntry).where(IncomeEntry.id == income_id, IncomeEntry.user_id == user_id))
    return result.scalar_one_or_none()


# Returns whether the user has any income entry (cheap existence check for onboarding).
async def exists_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(IncomeEntry.id).where(IncomeEntry.user_id == user_id).limit(1))
    return result.first() is not None


# Returns whether any income links this account (used to lock the account's currency once linked).
async def exists_by_account_id(session: AsyncSession, account_id: int, user_id: int) -> bool:
    result = await session.execute(select(IncomeEntry.id).where(IncomeEntry.account_id == account_id, IncomeEntry.user_id == user_id).limit(1))
    return result.first() is not None


# Returns the user's income dedup tuples (date, amount, currency, category, notes), used to flag
# duplicates on import. Column order matches INCOME_SPEC.dedup_fields.
async def list_dedup_keys_by_user(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[date_type, Decimal, str, IncomeCategory | None, str | None]]:
    result = await session.execute(
        select(
            IncomeEntry.date,
            IncomeEntry.amount,
            IncomeEntry.currency,
            IncomeEntry.category,
            IncomeEntry.notes,
        ).where(IncomeEntry.user_id == user_id)
    )
    return [(row[0], row[1], row[2], row[3], row[4]) for row in result.all()]


# Insert a new income entry.
async def create(session: AsyncSession, entry: IncomeEntry) -> IncomeEntry:
    session.add(entry)
    await session.flush()
    return entry


# Bulk-inserts new income entries and flushes to assign ids. Returns the inserted entries.
async def bulk_create(session: AsyncSession, entries: list[IncomeEntry]) -> list[IncomeEntry]:
    if not entries:
        return []
    session.add_all(entries)
    await session.flush()
    return entries


# Stage an income entry for update (caller commits).
async def save(session: AsyncSession, entry: IncomeEntry) -> None:
    session.add(entry)


# Delete an income entry.
async def delete(session: AsyncSession, entry: IncomeEntry) -> None:
    await session.delete(entry)


# Earliest income entry date for a user. Returns None when the user has no income entries.
# Used by the liquidity alert to size the income window during early app life.
async def get_first_income_date(session: AsyncSession, user_id: int) -> date_type | None:
    stmt = select(func.min(IncomeEntry.date)).where(IncomeEntry.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# Total income for a user within a date range, grouped by currency.
async def sum_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[str, Decimal]:
    stmt = (
        select(
            IncomeEntry.currency,
            func.coalesce(func.sum(IncomeEntry.amount), 0),
        )
        .where(IncomeEntry.user_id == user_id)
        .group_by(IncomeEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(IncomeEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(IncomeEntry.date <= date_to)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


# Sum of income linked to each account, grouped by account_id. Returns {account_id: total}.
# Every linked row is in the account's currency (enforced at link time), so no currency split.
# as_of_date bounds the sum to rows dated on or before it (used by reconciliation's point-in-time balance).
async def sum_by_account_ids(
    session: AsyncSession,
    account_ids: list[int],
    user_id: int,
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = select(IncomeEntry.account_id, func.coalesce(func.sum(IncomeEntry.amount), 0)).where(
        IncomeEntry.account_id.in_(account_ids), IncomeEntry.user_id == user_id
    )
    if as_of_date is not None:
        stmt = stmt.where(IncomeEntry.date <= as_of_date)
    result = await session.execute(stmt.group_by(IncomeEntry.account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Monthly income totals linked to each account, grouped by account_id, year, month (the account's
# currency is fixed, so no currency dimension). Returns a list of (account_id, year, month, total).
async def sum_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    if not account_ids:
        return []
    year_col = func.extract("year", IncomeEntry.date).label("year")
    month_col = func.extract("month", IncomeEntry.date).label("month")
    result = await session.execute(
        select(IncomeEntry.account_id, year_col, month_col, func.coalesce(func.sum(IncomeEntry.amount), 0))
        .where(IncomeEntry.account_id.in_(account_ids), IncomeEntry.user_id == user_id)
        .group_by(IncomeEntry.account_id, year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), Decimal(str(row[3]))) for row in result.all()]


# Monthly income totals for a user grouped by currency.
# Returns a list of (year, month, currency, total) tuples.
async def sum_by_user_monthly(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[int, int, str, Decimal]]:
    year_col = func.extract("year", IncomeEntry.date).label("year")
    month_col = func.extract("month", IncomeEntry.date).label("month")
    stmt = (
        select(
            year_col,
            month_col,
            IncomeEntry.currency,
            func.coalesce(func.sum(IncomeEntry.amount), 0),
        )
        .where(IncomeEntry.user_id == user_id)
        .group_by(year_col, month_col, IncomeEntry.currency)
        .order_by(year_col, month_col)
    )
    if date_from is not None:
        stmt = stmt.where(IncomeEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(IncomeEntry.date <= date_to)
    result = await session.execute(stmt)
    return [(int(row[0]), int(row[1]), row[2], row[3]) for row in result.all()]


# Income totals grouped by category for a user within a date range. NULL categories are
# coalesced into the synthetic key 'uncategorized' so the breakdown covers every row
# (the column is a native PG enum, so the coalesce happens in the row mapper, not SQL).
# Returns a list of (category, currency, total) tuples.
async def sum_by_user_grouped_by_category(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[str, str, Decimal]]:
    stmt = (
        select(
            IncomeEntry.category,
            IncomeEntry.currency,
            func.coalesce(func.sum(IncomeEntry.amount), 0),
        )
        .where(IncomeEntry.user_id == user_id)
        .group_by(IncomeEntry.category, IncomeEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(IncomeEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(IncomeEntry.date <= date_to)
    result = await session.execute(stmt)
    return [("uncategorized" if row[0] is None else str(row[0]), row[1], row[2]) for row in result.all()]


# Namespace to call repository functions (e.g. income_repository.list_by_user_filtered).
class IncomeRepository:
    bulk_create = staticmethod(bulk_create)
    create = staticmethod(create)
    delete = staticmethod(delete)
    exists_by_account_id = staticmethod(exists_by_account_id)
    exists_by_user = staticmethod(exists_by_user)
    get_by_id = staticmethod(get_by_id)
    get_first_income_date = staticmethod(get_first_income_date)
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    list_dedup_keys_by_user = staticmethod(list_dedup_keys_by_user)
    save = staticmethod(save)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_monthly = staticmethod(sum_by_account_ids_monthly)
    sum_by_user = staticmethod(sum_by_user)
    sum_by_user_grouped_by_category = staticmethod(sum_by_user_grouped_by_category)
    sum_by_user_monthly = staticmethod(sum_by_user_monthly)


# Singleton used by services to access income persistence.
income_repository = IncomeRepository()
