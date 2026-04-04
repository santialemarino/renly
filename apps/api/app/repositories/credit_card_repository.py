from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.credit_card import CreditCard


# List all credit cards for a user.
async def list_by_user(session: AsyncSession, user_id: int) -> list[CreditCard]:
    result = await session.execute(select(CreditCard).where(CreditCard.user_id == user_id).order_by(CreditCard.name))
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
