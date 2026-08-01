from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
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


# Sum of settlements drawn from each account, grouped by account_id. Returns {account_id: total}.
# Every linked settlement is in the account's currency (enforced at link time), so no currency split.
# as_of_date bounds the sum to rows dated on or before it (used by reconciliation's point-in-time balance).
# The join bounds it BELOW by the account's own opening_date: opening_balance is by definition the balance
# AT that date, so an earlier row is already inside it and summing it again double-counts.
async def sum_by_account_ids(
    session: AsyncSession,
    account_ids: list[int],
    user_id: int,
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = (
        select(CardSettlement.account_id, func.coalesce(func.sum(CardSettlement.amount), 0))
        .join(Account, Account.id == CardSettlement.account_id)
        .where(CardSettlement.account_id.in_(account_ids), CardSettlement.user_id == user_id, CardSettlement.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(CardSettlement.date <= as_of_date)
    result = await session.execute(stmt.group_by(CardSettlement.account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Returns whether any settlement draws from this account (used to lock the account's currency once linked).
async def exists_by_account_id(session: AsyncSession, account_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(CardSettlement.id).where(CardSettlement.account_id == account_id, CardSettlement.user_id == user_id).limit(1)
    )
    return result.first() is not None


# Monthly settlement totals drawn from each account, grouped by account_id, year, month (the
# account's currency is fixed). Returns a list of (account_id, year, month, total).
async def sum_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    if not account_ids:
        return []
    year_col = func.extract("year", CardSettlement.date).label("year")
    month_col = func.extract("month", CardSettlement.date).label("month")
    result = await session.execute(
        select(CardSettlement.account_id, year_col, month_col, func.coalesce(func.sum(CardSettlement.amount), 0))
        .join(Account, Account.id == CardSettlement.account_id)
        .where(CardSettlement.account_id.in_(account_ids), CardSettlement.user_id == user_id, CardSettlement.date >= Account.opening_date)
        .group_by(CardSettlement.account_id, year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), Decimal(str(row[3]))) for row in result.all()]


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


# Which of the given accounts have any linked settlement row at all. Drives the currency lock, so unlike
# sum_by_account_ids it is NOT bounded by opening_date: a pre-opening row contributes nothing to the
# balance but is still denominated in the account's currency.
async def linked_account_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(CardSettlement.account_id)
        .where(CardSettlement.account_id.in_(account_ids), CardSettlement.user_id == user_id)
        .group_by(CardSettlement.account_id)
    )
    return {row[0] for row in result.all()}


# Namespace to call repository functions (e.g. card_settlement_repository.list_by_card).
class CardSettlementRepository:
    list_by_card = staticmethod(list_by_card)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    delete = staticmethod(delete)
    exists_by_account_id = staticmethod(exists_by_account_id)
    linked_account_ids = staticmethod(linked_account_ids)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_monthly = staticmethod(sum_by_account_ids_monthly)
    sum_by_card_ids_grouped = staticmethod(sum_by_card_ids_grouped)
    sum_by_card_ids_monthly = staticmethod(sum_by_card_ids_monthly)


# Singleton used by services to access card settlement persistence.
card_settlement_repository = CardSettlementRepository()
