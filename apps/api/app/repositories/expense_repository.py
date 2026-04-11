from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.expense_entry import ExpenseCategory, ExpenseEntry


# List expenses for a user with optional filters and pagination.
async def list_by_user_filtered(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    category: ExpenseCategory | None = None,
    payment_method: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[ExpenseEntry], int]:
    base = select(ExpenseEntry).where(ExpenseEntry.user_id == user_id)

    if search:
        base = base.where(ExpenseEntry.notes.ilike(f"%{search}%"))
    if category is not None:
        base = base.where(ExpenseEntry.category == category)
    if payment_method is not None:
        base = base.where(ExpenseEntry.payment_method == payment_method)
    if date_from is not None:
        base = base.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        base = base.where(ExpenseEntry.date <= date_to)

    count_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    query = base.order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    return list(result.scalars().all()), total


# Get a single expense by id and user_id.
async def get_by_id(session: AsyncSession, expense_id: int, user_id: int) -> ExpenseEntry | None:
    result = await session.execute(select(ExpenseEntry).where(ExpenseEntry.id == expense_id, ExpenseEntry.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new expense entry.
async def create(session: AsyncSession, entry: ExpenseEntry) -> ExpenseEntry:
    session.add(entry)
    await session.flush()
    return entry


# Stage an expense entry for update (caller commits).
async def save(session: AsyncSession, entry: ExpenseEntry) -> None:
    session.add(entry)


# Delete an expense entry.
async def delete(session: AsyncSession, entry: ExpenseEntry) -> None:
    await session.delete(entry)


# Count expenses linked to a specific credit card.
async def count_by_credit_card(session: AsyncSession, credit_card_id: int) -> int:
    result = await session.execute(select(func.count()).where(ExpenseEntry.credit_card_id == credit_card_id))
    return int(result.scalar_one())


# Count expenses grouped by credit card id. Returns {card_id: count}.
async def count_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, int]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            func.count(),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Sum of expenses grouped by credit card id and currency. Returns {card_id: {currency: total}}.
async def sum_by_credit_card_ids_grouped(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> dict[int, dict[str, float]]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id, ExpenseEntry.currency)
    )
    grouped: dict[int, dict[str, float]] = {}
    for card_id, currency, total in result.all():
        grouped.setdefault(card_id, {})[currency] = float(total)
    return grouped


# Monthly expense totals for given credit cards, grouped by card_id, year, month, and currency.
# Returns a list of (card_id, year, month, currency, total) tuples.
async def sum_by_credit_card_ids_monthly(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> list[tuple[int, int, int, str, float]]:
    if not credit_card_ids:
        return []
    year_col = func.extract("year", ExpenseEntry.date).label("year")
    month_col = func.extract("month", ExpenseEntry.date).label("month")
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            year_col,
            month_col,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id, year_col, month_col, ExpenseEntry.currency)
        .order_by(year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], float(row[4])) for row in result.all()]


# Total expenses for a user within a date range.
async def sum_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[str, float]:
    stmt = (
        select(
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.user_id == user_id)
        .group_by(ExpenseEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExpenseEntry.date <= date_to)
    result = await session.execute(stmt)
    return {row[0]: float(row[1]) for row in result.all()}


# Monthly expense totals for a user grouped by currency.
# Returns a list of (year, month, currency, total) tuples.
async def sum_by_user_monthly(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[int, int, str, float]]:
    year_col = func.extract("year", ExpenseEntry.date).label("year")
    month_col = func.extract("month", ExpenseEntry.date).label("month")
    stmt = (
        select(
            year_col,
            month_col,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.user_id == user_id)
        .group_by(year_col, month_col, ExpenseEntry.currency)
        .order_by(year_col, month_col)
    )
    if date_from is not None:
        stmt = stmt.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExpenseEntry.date <= date_to)
    result = await session.execute(stmt)
    return [(int(row[0]), int(row[1]), row[2], float(row[3])) for row in result.all()]


# Expense totals grouped by category for a user within a date range.
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
            ExpenseEntry.category,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.user_id == user_id, ExpenseEntry.category.isnot(None))
        .group_by(ExpenseEntry.category, ExpenseEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExpenseEntry.date <= date_to)
    result = await session.execute(stmt)
    return [(str(row[0]), row[1], float(row[2])) for row in result.all()]


# Namespace to call repository functions (e.g. expense_repository.list_by_user_filtered).
class ExpenseRepository:
    count_by_credit_card = staticmethod(count_by_credit_card)
    count_by_credit_card_ids = staticmethod(count_by_credit_card_ids)
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    save = staticmethod(save)
    sum_by_credit_card_ids_grouped = staticmethod(sum_by_credit_card_ids_grouped)
    sum_by_credit_card_ids_monthly = staticmethod(sum_by_credit_card_ids_monthly)
    sum_by_user = staticmethod(sum_by_user)
    sum_by_user_grouped_by_category = staticmethod(sum_by_user_grouped_by_category)
    sum_by_user_monthly = staticmethod(sum_by_user_monthly)


# Singleton used by services to access expense persistence.
expense_repository = ExpenseRepository()
