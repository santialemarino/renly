from datetime import date as date_type

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


# Insert a new income entry.
async def create(session: AsyncSession, entry: IncomeEntry) -> IncomeEntry:
    session.add(entry)
    await session.flush()
    return entry


# Stage an income entry for update (caller commits).
async def save(session: AsyncSession, entry: IncomeEntry) -> None:
    session.add(entry)


# Delete an income entry.
async def delete(session: AsyncSession, entry: IncomeEntry) -> None:
    await session.delete(entry)


# Total income for a user within a date range, grouped by currency.
async def sum_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[str, float]:
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
    return {row[0]: float(row[1]) for row in result.all()}


# Monthly income totals for a user grouped by currency.
# Returns a list of (year, month, currency, total) tuples.
async def sum_by_user_monthly(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[int, int, str, float]]:
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
    return [(int(row[0]), int(row[1]), row[2], float(row[3])) for row in result.all()]


# Income totals grouped by category for a user within a date range.
# Returns a list of (category, currency, total) tuples.
async def sum_by_user_grouped_by_category(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[str, str, float]]:
    stmt = (
        select(
            IncomeEntry.category,
            IncomeEntry.currency,
            func.coalesce(func.sum(IncomeEntry.amount), 0),
        )
        .where(IncomeEntry.user_id == user_id, IncomeEntry.category.isnot(None))
        .group_by(IncomeEntry.category, IncomeEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(IncomeEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(IncomeEntry.date <= date_to)
    result = await session.execute(stmt)
    return [(str(row[0]), row[1], float(row[2])) for row in result.all()]


# Namespace to call repository functions (e.g. income_repository.list_by_user_filtered).
class IncomeRepository:
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    sum_by_user = staticmethod(sum_by_user)
    sum_by_user_grouped_by_category = staticmethod(sum_by_user_grouped_by_category)
    sum_by_user_monthly = staticmethod(sum_by_user_monthly)


# Singleton used by services to access income persistence.
income_repository = IncomeRepository()
