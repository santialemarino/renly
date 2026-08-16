from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.credit_card import CreditCard
from app.repositories.utils import apply_listing_filters

_SORT_COLUMNS = {
    "name": CreditCard.name,
    "closing_day": CreditCard.closing_day,
    "due_day": CreditCard.due_day,
    "currency": CreditCard.currency,
}


# List credit cards for a user with optional search, sorting, and archive filtering.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[CreditCard]:
    stmt = apply_listing_filters(
        select(CreditCard),
        CreditCard,
        user_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
        include_ids=None,
        sort_columns=_SORT_COLUMNS,
        default_order=CreditCard.name,
    )
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


# Counts the credit cards naming this account as their default funding account. Backs the currency lock:
# a default whose currency stops matching silently stops applying, so the change is refused instead.
async def count_by_default_account(session: AsyncSession, account_id: int, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(
            CreditCard.default_account_id == account_id,
            CreditCard.user_id == user_id,
        )
    )
    return result.scalar_one()


# Namespace to call repository functions (e.g. credit_card_repository.list_by_user).
class CreditCardRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    count_by_default_account = staticmethod(count_by_default_account)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access credit card persistence.
credit_card_repository = CreditCardRepository()
