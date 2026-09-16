from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.card_reconciliation import CardReconciliation
from app.models.card_settlement import CardSettlement
from app.models.expense_entry import ExpenseEntry
from app.models.shared_expense import SharedExpense
from app.utils.pagination import DEFAULT_PAGE_SIZE, apply_page


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


# List one page of a card's reconciliations, newest first, with the total across every page.
#
# Its own function rather than page parameters on list_by_card, because that one's other caller builds
# the statement list and matches a reconciliation to each period it drew — it needs every row, and a
# page of them would silently show periods as unreconciled.
async def list_page_by_card(
    session: AsyncSession,
    card_id: int,
    *,
    currency: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[CardReconciliation], int]:
    stmt = select(CardReconciliation).where(CardReconciliation.card_id == card_id)
    if currency is not None:
        stmt = stmt.where(CardReconciliation.currency == currency)
    count_result = await session.execute(select(func.count()).select_from(stmt.subquery()))
    ordered = stmt.order_by(CardReconciliation.period_end.desc(), CardReconciliation.id.desc())
    result = await session.execute(apply_page(ordered, page, page_size))
    return list(result.scalars().all()), count_result.scalar_one()


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


# Return every reconciliation whose recorded balance depends on rows dated target_date, for a given
# (card, currency). Used by the stale-detection hooks.
#
# The bound is period_end >= target_date, NOT "the period contains the date". A reconciliation's
# computed_balance comes from compute_bucket_balance_at(period_end), which sums everything dated
# <= period_end from the beginning of the bucket's history — the period bounds only name WHICH
# statement, they do not scope the arithmetic. So a row dated before a reconciled period still moves
# that period's balance, and the old period-contains predicate silently missed it.
async def list_affected_by_date(
    session: AsyncSession,
    card_id: int,
    currency: str,
    target_date: date_type,
) -> list[CardReconciliation]:
    result = await session.execute(
        select(CardReconciliation).where(
            CardReconciliation.card_id == card_id,
            CardReconciliation.currency == currency,
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
#
# Both tables, and that is not optional: a group's shared expense charged to this card raises the same
# liability a private one does and is already inside the card's RUNNING balance. Reading only
# expense_entries here would make a statement's balance disagree with the card's by exactly the
# group's charges — a reconcile dialog showing a figure the card page contradicts, and a Payments
# Calendar card_due short by the same amount.
#
# Card-side on both sides: it reads `amount`, never a cash leg. The bank cleared the bill in the
# bucket's own currency whatever it debited anyone.
async def sum_expenses_at(
    session: AsyncSession,
    card_id: int,
    currency: str,
    as_of_date: date_type,
) -> Decimal:
    private = select(func.coalesce(func.sum(ExpenseEntry.amount), 0)).where(
        ExpenseEntry.credit_card_id == card_id,
        ExpenseEntry.currency == currency,
        ExpenseEntry.date <= as_of_date,
    )
    shared = select(func.coalesce(func.sum(SharedExpense.amount), 0)).where(
        SharedExpense.credit_card_id == card_id,
        SharedExpense.currency == currency,
        SharedExpense.date <= as_of_date,
    )
    result = await session.execute(private)
    shared_result = await session.execute(shared)
    return Decimal(str(result.scalar_one())) + Decimal(str(shared_result.scalar_one()))


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
#
# Unioned over both expense tables for the same reason sum_expenses_at is, and the union happens in
# SQL rather than by merging two lists here: the caller cumulative-sums these in order, so two rows
# for one date would each be added to the running total and the statement would read correctly only by
# accident of ordering. One row per date is what the caller's contract actually is.
async def list_expense_daily_sums(
    session: AsyncSession,
    card_id: int,
    currency: str,
    up_to: date_type,
) -> list[tuple[date_type, Decimal]]:
    private = select(ExpenseEntry.date.label("date"), ExpenseEntry.amount.label("amount")).where(
        ExpenseEntry.credit_card_id == card_id,
        ExpenseEntry.currency == currency,
        ExpenseEntry.date <= up_to,
    )
    shared = select(SharedExpense.date.label("date"), SharedExpense.amount.label("amount")).where(
        SharedExpense.credit_card_id == card_id,
        SharedExpense.currency == currency,
        SharedExpense.date <= up_to,
    )
    charges = union_all(private, shared).subquery()
    result = await session.execute(select(charges.c.date, func.sum(charges.c.amount)).group_by(charges.c.date).order_by(charges.c.date))
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
#
# Unions a group's charges with the owner's own, exactly as sum_expenses_at and list_expense_daily_sums
# do. It did not, and the reason is worth keeping: this function was written in July as the batched
# sibling of sum_expenses_at, BEFORE a shared expense could name a card at all — so when shared money
# taught the other two about them it was the one nobody thought to look at. A function that predates a
# feature is exactly where an enumerated list goes stale. The consequence was that the Payments
# Calendar priced a card_due below the bill while the same bucket's statement and its balance on
# /credit-cards both counted the shared charge. A card's whole charge is its owner's liability whoever
# consumed what it bought, and there is no user filter for the same reason those two have none: the
# rows belong to the group, RLS scopes them, and a card only ever carries its own owner's charges.
async def sum_expenses_by_bucket_at(
    session: AsyncSession,
    card_ids: list[int],
    as_of_date: date_type,
) -> dict[tuple[int, str], Decimal]:
    if not card_ids:
        return {}
    private = select(
        ExpenseEntry.credit_card_id.label("card_id"),
        ExpenseEntry.currency.label("currency"),
        ExpenseEntry.amount.label("amount"),
    ).where(ExpenseEntry.credit_card_id.in_(card_ids), ExpenseEntry.date <= as_of_date)
    shared = select(
        SharedExpense.credit_card_id.label("card_id"),
        SharedExpense.currency.label("currency"),
        SharedExpense.amount.label("amount"),
    ).where(SharedExpense.credit_card_id.in_(card_ids), SharedExpense.date <= as_of_date)
    charges = union_all(private, shared).subquery()
    result = await session.execute(
        select(charges.c.card_id, charges.c.currency, func.sum(charges.c.amount)).group_by(charges.c.card_id, charges.c.currency)
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


# Earliest date of any activity (expense, shared expense or settlement) on a card+currency bucket.
# Returns None when the bucket has no activity yet. Drives the visibility rule for the statements list
# — we hide pre-history zeros (statements whose period_end is before the bucket existed).
#
# A group's charge counts as activity for the same reason it counts in the balance: it is the card
# owner's liability. Without it a bucket whose only charges are shared reads as having no history at
# all, and every statement carrying a real balance is hidden as a pre-history zero.
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
    shared_min = await session.execute(
        select(func.min(SharedExpense.date)).where(
            SharedExpense.credit_card_id == card_id,
            SharedExpense.currency == currency,
        )
    )
    settlement_min = await session.execute(
        select(func.min(CardSettlement.date)).where(
            CardSettlement.credit_card_id == card_id,
            CardSettlement.currency == currency,
        )
    )
    candidates = [d for d in (expense_min.scalar_one(), shared_min.scalar_one(), settlement_min.scalar_one()) if d is not None]
    return min(candidates) if candidates else None


# Namespace to call repository functions (e.g. card_reconciliation_repository.list_by_card).
class CardReconciliationRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    get_by_period = staticmethod(get_by_period)
    get_first_activity_date = staticmethod(get_first_activity_date)
    list_affected_by_date = staticmethod(list_affected_by_date)
    list_by_card = staticmethod(list_by_card)
    list_expense_daily_sums = staticmethod(list_expense_daily_sums)
    list_page_by_card = staticmethod(list_page_by_card)
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
