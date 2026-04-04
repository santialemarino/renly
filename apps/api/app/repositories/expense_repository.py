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


# Sum of expenses linked to a specific credit card.
async def sum_by_credit_card(session: AsyncSession, credit_card_id: int) -> float:
    result = await session.execute(select(func.coalesce(func.sum(ExpenseEntry.amount), 0)).where(ExpenseEntry.credit_card_id == credit_card_id))
    return float(result.scalar_one())


# Sum of expenses grouped by credit card id. Returns a dict {card_id: total}.
async def sum_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, float]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id)
    )
    return {row[0]: float(row[1]) for row in result.all()}


# Namespace to call repository functions (e.g. expense_repository.list_by_user_filtered).
class ExpenseRepository:
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    sum_by_credit_card = staticmethod(sum_by_credit_card)
    sum_by_credit_card_ids = staticmethod(sum_by_credit_card_ids)


# Singleton used by services to access expense persistence.
expense_repository = ExpenseRepository()
