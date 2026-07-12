from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.card_reconciliation import CardReconciliation
from app.models.card_settlement import CardSettlement
from app.models.expense_entry import ExpenseEntry


# List all reconciliations for a card, optionally filtered to a single bucket. Ordered by period_end desc.
async def list_by_card(
    session: AsyncSession,
    card_id: int,
    *,
    currency: str | None = None,
) -> list[CardReconciliation]:
    stmt = select(CardReconciliation).where(CardReconciliation.card_id == card_id)
    if currency is not None:
        stmt = stmt.where(CardReconciliation.currency == currency)
    stmt = stmt.order_by(CardReconciliation.period_end.desc(), CardReconciliation.id.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single reconciliation by id and card.
async def get_by_id(session: AsyncSession, reconciliation_id: int, card_id: int) -> CardReconciliation | None:
    result = await session.execute(
        select(CardReconciliation).where(
            CardReconciliation.id == reconciliation_id,
            CardReconciliation.card_id == card_id,
        )
    )
    return result.scalar_one_or_none()


# Get the reconciliation for a specific (card, currency, period). Used by create-or-replace.
async def get_by_period(
    session: AsyncSession,
    card_id: int,
    currency: str,
    period_start: date_type,
    period_end: date_type,
) -> CardReconciliation | None:
    result = await session.execute(
        select(CardReconciliation).where(
            CardReconciliation.card_id == card_id,
            CardReconciliation.currency == currency,
            CardReconciliation.period_start == period_start,
            CardReconciliation.period_end == period_end,
        )
    )
    return result.scalar_one_or_none()


# Return reconciliations whose period contains the given date for a given (card, currency).
# Used by stale-detection hooks: any retroactive edit to an expense / settlement inside this list's
# periods marks those reconciliations as stale.
async def list_covering_date(
    session: AsyncSession,
    card_id: int,
    currency: str,
    target_date: date_type,
) -> list[CardReconciliation]:
    result = await session.execute(
        select(CardReconciliation).where(
            CardReconciliation.card_id == card_id,
            CardReconciliation.currency == currency,
            CardReconciliation.period_start <= target_date,
            CardReconciliation.period_end >= target_date,
        )
    )
    return list(result.scalars().all())


# Insert a new reconciliation.
async def create(session: AsyncSession, reconciliation: CardReconciliation) -> CardReconciliation:
    session.add(reconciliation)
    await session.flush()
    return reconciliation


# Stage a reconciliation for update (caller commits).
async def save(session: AsyncSession, reconciliation: CardReconciliation) -> None:
    session.add(reconciliation)


# Delete a reconciliation. Cascades to its adjustment expense or income via FK.
async def delete(session: AsyncSession, reconciliation: CardReconciliation) -> None:
    await session.delete(reconciliation)


# Bulk-mark a set of reconciliations as stale (id list). Used by stale-detection hooks.
async def mark_stale(session: AsyncSession, reconciliation_ids: list[int]) -> None:
    if not reconciliation_ids:
        return
    await session.execute(update(CardReconciliation).where(CardReconciliation.id.in_(reconciliation_ids)).values(is_stale=True))


# Sum of expenses for a card+currency bucket dated at or before as_of_date.
# Used by compute_bucket_balance_at — the running-balance snapshot at a statement's closing date.
async def sum_expenses_at(
    session: AsyncSession,
    card_id: int,
    currency: str,
    as_of_date: date_type,
) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(ExpenseEntry.amount), 0)).where(
            ExpenseEntry.credit_card_id == card_id,
            ExpenseEntry.currency == currency,
            ExpenseEntry.date <= as_of_date,
        )
    )
    return Decimal(str(result.scalar_one()))


# Sum of settlements for a card+currency bucket dated at or before as_of_date.
# Mirrors sum_expenses_at — both feed the running-balance snapshot.
async def sum_settlements_at(
    session: AsyncSession,
    card_id: int,
    currency: str,
    as_of_date: date_type,
) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(CardSettlement.amount), 0)).where(
            CardSettlement.credit_card_id == card_id,
            CardSettlement.currency == currency,
            CardSettlement.date <= as_of_date,
        )
    )
    return Decimal(str(result.scalar_one()))


# Sum of settlements for a card+currency bucket dated inside (after_date, to_date].
# Used by the Payments Calendar card_due event to decide whether the statement due on
# to_date has been settled (paid-marking; the frozen statement amount is unchanged).
async def sum_settlements_between(
    session: AsyncSession,
    card_id: int,
    currency: str,
    after_date: date_type,
    to_date: date_type,
) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(CardSettlement.amount), 0)).where(
            CardSettlement.credit_card_id == card_id,
            CardSettlement.currency == currency,
            CardSettlement.date > after_date,
            CardSettlement.date <= to_date,
        )
    )
    return Decimal(str(result.scalar_one()))


# Per-day expense sums for a card+currency bucket up to a date, ascending. One grouped query
# replaces the per-closing SUM round-trips in list_recent_statements; the service cumulative-sums
# the daily rows to get the running balance at each statement closing.
async def list_expense_daily_sums(
    session: AsyncSession,
    card_id: int,
    currency: str,
    up_to: date_type,
) -> list[tuple[date_type, Decimal]]:
    result = await session.execute(
        select(ExpenseEntry.date, func.sum(ExpenseEntry.amount))
        .where(
            ExpenseEntry.credit_card_id == card_id,
            ExpenseEntry.currency == currency,
            ExpenseEntry.date <= up_to,
        )
        .group_by(ExpenseEntry.date)
        .order_by(ExpenseEntry.date)
    )
    return [(row[0], Decimal(str(row[1]))) for row in result.all()]


# Mirrors list_expense_daily_sums for settlements.
async def list_settlement_daily_sums(
    session: AsyncSession,
    card_id: int,
    currency: str,
    up_to: date_type,
) -> list[tuple[date_type, Decimal]]:
    result = await session.execute(
        select(CardSettlement.date, func.sum(CardSettlement.amount))
        .where(
            CardSettlement.credit_card_id == card_id,
            CardSettlement.currency == currency,
            CardSettlement.date <= up_to,
        )
        .group_by(CardSettlement.date)
        .order_by(CardSettlement.date)
    )
    return [(row[0], Decimal(str(row[1]))) for row in result.all()]


# Sums expenses per (card_id, currency) bucket dated at or before as_of_date, for many cards in
# one grouped query. Returns {(card_id, currency): sum}; buckets with no rows are simply absent.
async def sum_expenses_by_bucket_at(
    session: AsyncSession,
    card_ids: list[int],
    as_of_date: date_type,
) -> dict[tuple[int, str], Decimal]:
    if not card_ids:
        return {}
    result = await session.execute(
        select(ExpenseEntry.credit_card_id, ExpenseEntry.currency, func.sum(ExpenseEntry.amount))
        .where(ExpenseEntry.credit_card_id.in_(card_ids), ExpenseEntry.date <= as_of_date)
        .group_by(ExpenseEntry.credit_card_id, ExpenseEntry.currency)
    )
    return {(row[0], row[1]): Decimal(str(row[2])) for row in result.all()}


# Mirrors sum_expenses_by_bucket_at for settlements.
async def sum_settlements_by_bucket_at(
    session: AsyncSession,
    card_ids: list[int],
    as_of_date: date_type,
) -> dict[tuple[int, str], Decimal]:
    if not card_ids:
        return {}
    result = await session.execute(
        select(CardSettlement.credit_card_id, CardSettlement.currency, func.sum(CardSettlement.amount))
        .where(CardSettlement.credit_card_id.in_(card_ids), CardSettlement.date <= as_of_date)
        .group_by(CardSettlement.credit_card_id, CardSettlement.currency)
    )
    return {(row[0], row[1]): Decimal(str(row[2])) for row in result.all()}


# Earliest date of any activity (expense or settlement) on a card+currency bucket. Returns None
# when the bucket has no activity yet. Drives the visibility rule for the statements list — we
# hide pre-history zeros (statements whose period_end is before the bucket existed).
async def get_first_activity_date(
    session: AsyncSession,
    card_id: int,
    currency: str,
) -> date_type | None:
    expense_min = await session.execute(
        select(func.min(ExpenseEntry.date)).where(
            ExpenseEntry.credit_card_id == card_id,
            ExpenseEntry.currency == currency,
        )
    )
    settlement_min = await session.execute(
        select(func.min(CardSettlement.date)).where(
            CardSettlement.credit_card_id == card_id,
            CardSettlement.currency == currency,
        )
    )
    candidates = [d for d in (expense_min.scalar_one(), settlement_min.scalar_one()) if d is not None]
    return min(candidates) if candidates else None


# Namespace to call repository functions (e.g. card_reconciliation_repository.list_by_card).
class CardReconciliationRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    get_by_period = staticmethod(get_by_period)
    get_first_activity_date = staticmethod(get_first_activity_date)
    list_by_card = staticmethod(list_by_card)
    list_covering_date = staticmethod(list_covering_date)
    list_expense_daily_sums = staticmethod(list_expense_daily_sums)
    list_settlement_daily_sums = staticmethod(list_settlement_daily_sums)
    mark_stale = staticmethod(mark_stale)
    save = staticmethod(save)
    sum_expenses_at = staticmethod(sum_expenses_at)
    sum_expenses_by_bucket_at = staticmethod(sum_expenses_by_bucket_at)
    sum_settlements_at = staticmethod(sum_settlements_at)
    sum_settlements_between = staticmethod(sum_settlements_between)
    sum_settlements_by_bucket_at = staticmethod(sum_settlements_by_bucket_at)


# Singleton used by services to access card reconciliation persistence.
card_reconciliation_repository = CardReconciliationRepository()
