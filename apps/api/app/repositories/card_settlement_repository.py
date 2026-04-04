from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.card_settlement import CardSettlement


# List all settlements for a credit card.
async def list_by_card(session: AsyncSession, credit_card_id: int) -> list[CardSettlement]:
    result = await session.execute(
        select(CardSettlement).where(CardSettlement.credit_card_id == credit_card_id).order_by(CardSettlement.date.desc(), CardSettlement.id.desc())
    )
    return list(result.scalars().all())


# Get a single settlement by id and card.
async def get_by_id(session: AsyncSession, settlement_id: int, credit_card_id: int) -> CardSettlement | None:
    result = await session.execute(
        select(CardSettlement).where(
            CardSettlement.id == settlement_id,
            CardSettlement.credit_card_id == credit_card_id,
        )
    )
    return result.scalar_one_or_none()


# Insert a new settlement.
async def create(session: AsyncSession, settlement: CardSettlement) -> CardSettlement:
    session.add(settlement)
    await session.flush()
    return settlement


# Stage a settlement for update (caller commits).
async def save(session: AsyncSession, settlement: CardSettlement) -> None:
    session.add(settlement)


# Delete a settlement.
async def delete(session: AsyncSession, settlement: CardSettlement) -> None:
    await session.delete(settlement)


# Sum of settlements for a specific credit card.
async def sum_by_card(session: AsyncSession, credit_card_id: int) -> float:
    result = await session.execute(select(func.coalesce(func.sum(CardSettlement.amount), 0)).where(CardSettlement.credit_card_id == credit_card_id))
    return float(result.scalar_one())


# Sum of settlements grouped by credit card id. Returns a dict {card_id: total}.
async def sum_by_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, float]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            CardSettlement.credit_card_id,
            func.coalesce(func.sum(CardSettlement.amount), 0),
        )
        .where(CardSettlement.credit_card_id.in_(credit_card_ids))
        .group_by(CardSettlement.credit_card_id)
    )
    return {row[0]: float(row[1]) for row in result.all()}


# Namespace to call repository functions (e.g. card_settlement_repository.list_by_card).
class CardSettlementRepository:
    list_by_card = staticmethod(list_by_card)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    sum_by_card = staticmethod(sum_by_card)
    sum_by_card_ids = staticmethod(sum_by_card_ids)


# Singleton used by services to access card settlement persistence.
card_settlement_repository = CardSettlementRepository()
