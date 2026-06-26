from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

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


# Returns the user's expense dedup tuples (date, amount, currency, category, notes), used to flag
# duplicates on import. Column order matches EXPENSES_SPEC.dedup_fields.
async def list_dedup_keys_by_user(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[date_type, Decimal, str, ExpenseCategory | None, str | None]]:
    result = await session.execute(
        select(
            ExpenseEntry.date,
            ExpenseEntry.amount,
            ExpenseEntry.currency,
            ExpenseEntry.category,
            ExpenseEntry.notes,
        ).where(ExpenseEntry.user_id == user_id)
    )
    return [(row[0], row[1], row[2], row[3], row[4]) for row in result.all()]


# Insert a new expense entry.
async def create(session: AsyncSession, entry: ExpenseEntry) -> ExpenseEntry:
    session.add(entry)
    await session.flush()
    return entry


# Bulk-inserts new expense entries and flushes to assign ids. Returns the inserted entries.
async def bulk_create(session: AsyncSession, entries: list[ExpenseEntry]) -> list[ExpenseEntry]:
    if not entries:
        return []
    session.add_all(entries)
    await session.flush()
    return entries


# Stage an expense entry for update (caller commits).
async def save(session: AsyncSession, entry: ExpenseEntry) -> None:
    session.add(entry)


# Delete an expense entry.
async def delete(session: AsyncSession, entry: ExpenseEntry) -> None:
    await session.delete(entry)


# Count expenses linked to a specific credit card.
async def count_by_credit_card(session: AsyncSession, credit_card_id: int) -> int:
    result = await session.execute(select(func.count()).where(ExpenseEntry.credit_card_id == credit_card_id))
    return int(result.scalar_one())


# Count expenses grouped by credit card id. Returns {card_id: count}.
async def count_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, int]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            func.count(),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Sum of expenses grouped by credit card id and currency. Returns {card_id: {currency: total}}.
async def sum_by_credit_card_ids_grouped(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> dict[int, dict[str, float]]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id, ExpenseEntry.currency)
    )
    grouped: dict[int, dict[str, float]] = {}
    for card_id, currency, total in result.all():
        grouped.setdefault(card_id, {})[currency] = float(total)
    return grouped


# Monthly expense totals for given credit cards, grouped by card_id, year, month, and currency.
# Returns a list of (card_id, year, month, currency, total) tuples.
async def sum_by_credit_card_ids_monthly(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> list[tuple[int, int, int, str, float]]:
    if not credit_card_ids:
        return []
    year_col = func.extract("year", ExpenseEntry.date).label("year")
    month_col = func.extract("month", ExpenseEntry.date).label("month")
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            year_col,
            month_col,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.credit_card_id.in_(credit_card_ids))
        .group_by(ExpenseEntry.credit_card_id, year_col, month_col, ExpenseEntry.currency)
        .order_by(year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], float(row[4])) for row in result.all()]


# Total expenses for a user within a date range.
async def sum_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[str, float]:
    stmt = (
        select(
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.user_id == user_id)
        .group_by(ExpenseEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExpenseEntry.date <= date_to)
    result = await session.execute(stmt)
    return {row[0]: float(row[1]) for row in result.all()}


# Monthly expense totals for a user grouped by currency.
# Returns a list of (year, month, currency, total) tuples.
async def sum_by_user_monthly(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[int, int, str, float]]:
    year_col = func.extract("year", ExpenseEntry.date).label("year")
    month_col = func.extract("month", ExpenseEntry.date).label("month")
    stmt = (
        select(
            year_col,
            month_col,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.user_id == user_id)
        .group_by(year_col, month_col, ExpenseEntry.currency)
        .order_by(year_col, month_col)
    )
    if date_from is not None:
        stmt = stmt.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExpenseEntry.date <= date_to)
    result = await session.execute(stmt)
    return [(int(row[0]), int(row[1]), row[2], float(row[3])) for row in result.all()]


# Expense totals grouped by category for a user within a date range.
# Returns a list of (category, currency, total) tuples.
async def sum_by_user_grouped_by_category(
    session: AsyncSession,
    user_id: int,
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[str, str, float]]:
    stmt = (
        select(
            ExpenseEntry.category,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(ExpenseEntry.user_id == user_id, ExpenseEntry.category.isnot(None))
        .group_by(ExpenseEntry.category, ExpenseEntry.currency)
    )
    if date_from is not None:
        stmt = stmt.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExpenseEntry.date <= date_to)
    result = await session.execute(stmt)
    return [(str(row[0]), row[1], float(row[2])) for row in result.all()]


# Finds the most recent auto-generated expense (source IN subscription / installment)
# matching the candidate manual entry on card / currency / amount within ±window_days.
# `exclude_expense_id` is set on the edit flow to prevent an expense from matching
# itself when it's already auto-tagged (e.g. user editing a scheduler-emitted row).
# Returns the first match newest-first, or None.
async def find_auto_charge_match(
    session: AsyncSession,
    user_id: int,
    *,
    credit_card_id: int,
    currency: str,
    amount: Decimal,
    target_date: date_type,
    window_days: int,
    exclude_expense_id: int | None = None,
) -> ExpenseEntry | None:
    lo = target_date - timedelta(days=window_days)
    hi = target_date + timedelta(days=window_days)
    # Require the source FK to be intact — otherwise the match has no plan name to
    # surface in the confirmation dialog. Rows whose source plan was deleted via
    # ON DELETE SET NULL keep `source='subscription'|'installment'` but lose the FK;
    # skip them so a slightly older valid match isn't shadowed by an unresolvable one.
    stmt = (
        select(ExpenseEntry)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.credit_card_id == credit_card_id)
        .where(ExpenseEntry.currency == currency)
        .where(ExpenseEntry.amount == amount)
        .where(ExpenseEntry.date >= lo)
        .where(ExpenseEntry.date <= hi)
        .where(
            ((ExpenseEntry.source == "subscription") & ExpenseEntry.subscription_id.is_not(None))
            | ((ExpenseEntry.source == "installment") & ExpenseEntry.installment_id.is_not(None))
        )
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
        .limit(1)
    )
    if exclude_expense_id is not None:
        stmt = stmt.where(ExpenseEntry.id != exclude_expense_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# Returns {obligation_id: [ExpenseEntry, ...]} for expenses linked to any of the
# given obligations, sorted by date DESC (newest first). Used by the Payments
# Calendar to size the backward-walk for the Paid badge AND to surface each paid
# cycle with its actual historical amount + currency (NOT the obligation's current
# values, which may have been edited since the payment).
async def list_linked_obligation_expenses(
    session: AsyncSession,
    user_id: int,
    obligation_ids: list[int],
) -> dict[int, list[ExpenseEntry]]:
    if not obligation_ids:
        return {}
    stmt = (
        select(ExpenseEntry)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.payment_obligation_id.in_(obligation_ids))
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
    )
    result = await session.execute(stmt)
    grouped: dict[int, list[ExpenseEntry]] = {}
    for entry in result.scalars().all():
        assert entry.payment_obligation_id is not None  # filtered by WHERE clause.
        grouped.setdefault(entry.payment_obligation_id, []).append(entry)
    return grouped


# Returns {obligation_id: date} for the most recent linked expense per obligation.
# Used by the payment-obligations list endpoint to surface a "Paid on" indicator
# on archived one-off rows (Phase 3, Step E, sub-improvement 6.i).
async def max_linked_obligation_dates(
    session: AsyncSession,
    user_id: int,
    obligation_ids: list[int],
) -> dict[int, date_type]:
    if not obligation_ids:
        return {}
    result = await session.execute(
        select(ExpenseEntry.payment_obligation_id, func.max(ExpenseEntry.date))
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.payment_obligation_id.in_(obligation_ids))
        .group_by(ExpenseEntry.payment_obligation_id)
    )
    return {row[0]: row[1] for row in result.all()}


# Returns {subscription_id: {date: ExpenseEntry}} for scheduler-emitted expenses linked
# to any of the given subscriptions, restricted to the [window_lo, window_hi] date range.
# Used by the Payments Calendar backward walker to pair past cycle dates with the
# actual auto-generated expense row for the Paid badge (symmetric to the obligation flow).
# Date-indexed because subscriptions enforce one expense per (subscription_id, date) via
# a partial UNIQUE INDEX — no need to handle multiples per cycle.
async def linked_subscription_expenses_by_date(
    session: AsyncSession,
    user_id: int,
    subscription_ids: list[int],
    window_lo: date_type,
    window_hi: date_type,
) -> dict[int, dict[date_type, ExpenseEntry]]:
    if not subscription_ids:
        return {}
    stmt = (
        select(ExpenseEntry)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.subscription_id.in_(subscription_ids))
        .where(ExpenseEntry.date >= window_lo)
        .where(ExpenseEntry.date <= window_hi)
    )
    result = await session.execute(stmt)
    grouped: dict[int, dict[date_type, ExpenseEntry]] = {}
    for entry in result.scalars().all():
        assert entry.subscription_id is not None  # filtered by WHERE clause.
        grouped.setdefault(entry.subscription_id, {})[entry.date] = entry
    return grouped


# Same shape as linked_subscription_expenses_by_date but for installments — one auto-row
# per (installment_id, date) (partial UNIQUE INDEX guarantees no duplicates).
async def linked_installment_expenses_by_date(
    session: AsyncSession,
    user_id: int,
    installment_ids: list[int],
    window_lo: date_type,
    window_hi: date_type,
) -> dict[int, dict[date_type, ExpenseEntry]]:
    if not installment_ids:
        return {}
    stmt = (
        select(ExpenseEntry)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.installment_id.in_(installment_ids))
        .where(ExpenseEntry.date >= window_lo)
        .where(ExpenseEntry.date <= window_hi)
    )
    result = await session.execute(stmt)
    grouped: dict[int, dict[date_type, ExpenseEntry]] = {}
    for entry in result.scalars().all():
        assert entry.installment_id is not None  # filtered by WHERE clause.
        grouped.setdefault(entry.installment_id, {})[entry.date] = entry
    return grouped


# Returns True when `expense_id` is the most-recent linked expense (by date DESC, id DESC)
# for the given obligation. Used by the reverse-on-unlink hook (Phase 3, follow-up Item 10):
# the obligation's cursor walks back only when the row being deleted / unlinked was the
# newest linked expense — middle-of-chain deletions leave the cursor alone. Single-query.
async def is_most_recent_linked_obligation_expense(
    session: AsyncSession,
    user_id: int,
    obligation_id: int,
    expense_id: int,
) -> bool:
    stmt = (
        select(ExpenseEntry.id)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.payment_obligation_id == obligation_id)
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    newest_id = result.scalar_one_or_none()
    return newest_id == expense_id


# Returns True when `expense_id` is the most-recent linked expense for the given subscription.
# Mirror of is_most_recent_linked_obligation_expense; same most-recent-only reverse rule.
async def is_most_recent_linked_subscription_expense(
    session: AsyncSession,
    user_id: int,
    subscription_id: int,
    expense_id: int,
) -> bool:
    stmt = (
        select(ExpenseEntry.id)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.subscription_id == subscription_id)
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    newest_id = result.scalar_one_or_none()
    return newest_id == expense_id


# Returns True when `expense_id` is the most-recent linked expense for the given installment.
# Mirror of is_most_recent_linked_obligation_expense; same most-recent-only reverse rule.
async def is_most_recent_linked_installment_expense(
    session: AsyncSession,
    user_id: int,
    installment_id: int,
    expense_id: int,
) -> bool:
    stmt = (
        select(ExpenseEntry.id)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.installment_id == installment_id)
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    newest_id = result.scalar_one_or_none()
    return newest_id == expense_id


# Namespace to call repository functions (e.g. expense_repository.list_by_user_filtered).
class ExpenseRepository:
    bulk_create = staticmethod(bulk_create)
    count_by_credit_card = staticmethod(count_by_credit_card)
    count_by_credit_card_ids = staticmethod(count_by_credit_card_ids)
    create = staticmethod(create)
    delete = staticmethod(delete)
    find_auto_charge_match = staticmethod(find_auto_charge_match)
    get_by_id = staticmethod(get_by_id)
    is_most_recent_linked_installment_expense = staticmethod(is_most_recent_linked_installment_expense)
    is_most_recent_linked_obligation_expense = staticmethod(is_most_recent_linked_obligation_expense)
    is_most_recent_linked_subscription_expense = staticmethod(is_most_recent_linked_subscription_expense)
    linked_installment_expenses_by_date = staticmethod(linked_installment_expenses_by_date)
    linked_subscription_expenses_by_date = staticmethod(linked_subscription_expenses_by_date)
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    list_dedup_keys_by_user = staticmethod(list_dedup_keys_by_user)
    list_linked_obligation_expenses = staticmethod(list_linked_obligation_expenses)
    max_linked_obligation_dates = staticmethod(max_linked_obligation_dates)
    save = staticmethod(save)
    sum_by_credit_card_ids_grouped = staticmethod(sum_by_credit_card_ids_grouped)
    sum_by_credit_card_ids_monthly = staticmethod(sum_by_credit_card_ids_monthly)
    sum_by_user = staticmethod(sum_by_user)
    sum_by_user_grouped_by_category = staticmethod(sum_by_user_grouped_by_category)
    sum_by_user_monthly = staticmethod(sum_by_user_monthly)


# Singleton used by services to access expense persistence.
expense_repository = ExpenseRepository()
