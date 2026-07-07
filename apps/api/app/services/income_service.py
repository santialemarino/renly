from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
from app.repositories import income_repository
from app.services import settings_service


# List income entries for a user with optional filters and pagination.
async def list_income(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    category: IncomeCategory | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[IncomeEntry], int]:
    return await income_repository.list_by_user_filtered(
        session,
        user.id,
        search=search,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


# Get a single income entry by id. Raises NotFoundError if not found.
async def get_income(session: AsyncSession, income_id: int, user: User) -> IncomeEntry:
    entry = await income_repository.get_by_id(session, income_id, user.id)
    if entry is None:
        raise NotFoundError("Income entry not found.")
    return entry


# Create a new income entry.
async def create_income(
    session: AsyncSession,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    category: IncomeCategory | None = None,
    notes: str | None = None,
    source: str = "manual",
) -> IncomeEntry:
    entry = IncomeEntry(
        user_id=user.id,
        date=date,
        amount=amount,
        currency=currency,
        category=category,
        notes=notes,
        source=source,
    )
    entry = await income_repository.create(session, entry)
    # Retire the income first-run sample once the user has their first income entry.
    await settings_service.retire_sample(session, user.id, "income")
    await session.commit()
    return entry


# Update an existing income entry. Only provided fields are changed.
async def update_income(
    session: AsyncSession,
    income_id: int,
    user: User,
    **fields: object,
) -> IncomeEntry:
    entry = await get_income(session, income_id, user)
    for key, value in fields.items():
        setattr(entry, key, value)
    await income_repository.save(session, entry)
    await session.commit()
    await session.refresh(entry)
    return entry


# Delete an income entry.
async def delete_income(session: AsyncSession, income_id: int, user: User) -> None:
    entry = await get_income(session, income_id, user)
    await income_repository.delete(session, entry)
    await session.commit()
