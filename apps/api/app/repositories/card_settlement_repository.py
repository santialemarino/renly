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


# Delete a settlement.
async def delete(session: AsyncSession, settlement: CardSettlement) -> None:
    await session.delete(settlement)


# Sum of settlements grouped by credit card id and currency. Returns {card_id: {currency: total}}.
# Replaces the flat sum_by_card_ids — bucket balances need per-currency totals.
async def sum_by_card_ids_grouped(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> dict[int, dict[str, float]]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            CardSettlement.credit_card_id,
            CardSettlement.currency,
            func.coalesce(func.sum(CardSettlement.amount), 0),
        )
        .where(CardSettlement.credit_card_id.in_(credit_card_ids))
        .group_by(CardSettlement.credit_card_id, CardSettlement.currency)
    )
    grouped: dict[int, dict[str, float]] = {}
    for card_id, currency, total in result.all():
        grouped.setdefault(card_id, {})[currency] = float(total)
    return grouped


# Monthly settlement totals for given credit cards, grouped by card_id, year, month, and currency.
# Returns a list of (card_id, year, month, currency, total) tuples.
async def sum_by_card_ids_monthly(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> list[tuple[int, int, int, str, float]]:
    if not credit_card_ids:
        return []
    year_col = func.extract("year", CardSettlement.date).label("year")
    month_col = func.extract("month", CardSettlement.date).label("month")
    result = await session.execute(
        select(
            CardSettlement.credit_card_id,
            year_col,
            month_col,
            CardSettlement.currency,
            func.coalesce(func.sum(CardSettlement.amount), 0),
        )
        .where(CardSettlement.credit_card_id.in_(credit_card_ids))
        .group_by(CardSettlement.credit_card_id, year_col, month_col, CardSettlement.currency)
        .order_by(year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], float(row[4])) for row in result.all()]


# Namespace to call repository functions (e.g. card_settlement_repository.list_by_card).
class CardSettlementRepository:
    list_by_card = staticmethod(list_by_card)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    delete = staticmethod(delete)
    sum_by_card_ids_grouped = staticmethod(sum_by_card_ids_grouped)
    sum_by_card_ids_monthly = staticmethod(sum_by_card_ids_monthly)


# Singleton used by services to access card settlement persistence.
card_settlement_repository = CardSettlementRepository()
