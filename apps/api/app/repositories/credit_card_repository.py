from sqlalchemy import asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.credit_card import CreditCard

_SORT_COLUMNS = {
    "name": CreditCard.name,
    "closing_day": CreditCard.closing_day,
    "due_day": CreditCard.due_day,
    "currency": CreditCard.currency,
}


# List credit cards for a user with optional search and sorting.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> list[CreditCard]:
    stmt = select(CreditCard).where(CreditCard.user_id == user_id)
    if search:
        stmt = stmt.where(CreditCard.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else CreditCard.name
    stmt = stmt.order_by(order_clause)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single credit card by id and user_id.
async def get_by_id(session: AsyncSession, card_id: int, user_id: int) -> CreditCard | None:
    result = await session.execute(select(CreditCard).where(CreditCard.id == card_id, CreditCard.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new credit card.
async def create(session: AsyncSession, card: CreditCard) -> CreditCard:
    session.add(card)
    await session.flush()
    return card


# Stage a credit card for update (caller commits).
async def save(session: AsyncSession, card: CreditCard) -> None:
    session.add(card)


# Delete a credit card.
async def delete(session: AsyncSession, card: CreditCard) -> None:
    await session.delete(card)


# Namespace to call repository functions (e.g. credit_card_repository.list_by_user).
class CreditCardRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access credit card persistence.
credit_card_repository = CreditCardRepository()
