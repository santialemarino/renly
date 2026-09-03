from datetime import date as date_type
from datetime import datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import String, cast, func, literal, null, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.shared_expense import SharedExpense, SharedExpenseSplit
from app.repositories.utils import apply_entry_sort

# The two things a row in the unioned expenses list can be. A private expense_entries row of the
# caller's own, or the caller's SHARE of a shared expense their group recorded.
SCOPE_PRIVATE = "private"
SCOPE_SHARED = "shared"

# What a shared row reports as its origin. `source` means "how did this get into Renly", and for a row
# that is one member's share of a group's expense there is no truer answer.
SOURCE_SHARED = "shared"


# The columns the list can be sorted by, read off the UNION's own projection.
#
# A function over the merged rows rather than a table-keyed constant, because the two branches read
# different tables and the sort applies to neither of them directly — a constant naming one table's
# columns would compile against a projection the query never sorts.
#
# `category` is sorted as TEXT, not as the enum: ORDER BY on a Postgres enum follows its DECLARATION
# order, which differs between a database built from 01_create_tables.sql and one built by migrations —
# the same rows would come back in a different order per environment. The values are alphabetical
# anyway, so the cast costs nothing.
def sort_columns(rows) -> dict:
    return {
        "date": rows.c.date,
        "amount": rows.c.amount,
        "category": cast(rows.c.category, String),
        "payment_method": rows.c.payment_method,
    }


# One row of the unioned expenses list, in the projection both branches produce.
#
# It is a flat projection rather than an ORM row because the two branches read different tables and
# neither is a superset of the other — hydrating each side back into its model would cost two more
# queries and hand the service two shapes to reconcile.
#
# Three fields carry the whole difference between the branches:
#   * `scope` says which table the row came from. It is also half the identity: `id` is unique within
#     each table but NOT across the union, so (scope, id) is the key and (scope, id) is the tie-break.
#   * `amount` is the caller's own figure either way — the whole expense when it is private, their
#     SHARE when it is shared, which is the one rule the flow half rests on (your share is your expense).
#   * `full_amount` is the shared expense's total, so a reader can say "your 30 of 90" without a second
#     request. Null on a private row, where the two would be the same number twice.
#
# `account_id` and `credit_card_id` are deliberately null on a shared row. They identify the PAYER's
# instrument, which is frequently another member's, and a row describing your share should not carry
# somebody else's card id. `payment_method` is kept, because it describes the expense rather than
# naming anyone's account.
class ExpenseListRow(NamedTuple):
    scope: str
    id: int
    date: date_type
    amount: Decimal
    currency: str
    category: ExpenseCategory | None
    notes: str | None
    payment_method: str | None
    credit_card_id: int | None
    account_id: int | None
    source: str
    payment_obligation_id: int | None
    subscription_id: int | None
    installment_id: int | None
    reconciliation_id: int | None
    account_reconciliation_id: int | None
    created_at: datetime
    updated_at: datetime
    group_id: int | None
    full_amount: Decimal | None


# The filters both branches of the list share, applied to whichever model carries them. Written once
# so a filter added to the private list cannot silently miss the shared one — the failure that a
# second copy of this block would eventually produce.
def _apply_list_filters(
    stmt,
    model,
    *,
    search: str | None,
    category: ExpenseCategory | None,
    payment_method: str | None,
    date_from: date_type | None,
    date_to: date_type | None,
):
    if search:
        stmt = stmt.where(model.notes.ilike(f"%{search}%"))
    if category is not None:
        stmt = stmt.where(model.category == category)
    if payment_method is not None:
        stmt = stmt.where(model.payment_method == payment_method)
    if date_from is not None:
        stmt = stmt.where(model.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(model.date <= date_to)
    return stmt


# Lists the caller's expenses: their own private rows, plus their SHARE of every shared expense their
# group seats take part in, as one paginated, sorted, filtered list.
#
# `member_ids` are the caller's own active group seats. When it is empty the shared branch is not built
# at all and the statement is exactly the private query this function has always run — a solo user (who
# is every user at launch) pays nothing for a union with no rows in it. The filters are applied by one
# helper to each branch, so the branches cannot drift even though only one of them is always present.
#
# The seats are resolved by the caller rather than joined here for a measured reason: joining
# group_members to filter the splits makes Postgres scan every split in the database, while an
# `IN (seat ids)` predicate uses the splits' member index. On a 55,000-row list that was the difference
# between ~20 ms and ~50 ms for one page.
#
# The tie-break is (id, scope) rather than id alone, because ids are unique per TABLE and this list
# spans two — without the scope a private row and a shared row sharing a date and an id would have no
# total order, and Postgres may then repeat one across pages or skip it entirely.#
# ▸ The tie-break is NOT observable by testing, and a mutation sweep proved it on both unions. Dropping
# the scope stays green even against a fixture built to force a genuine (date, id) collision between a
# private and a shared row, because an unstable sort is *permitted* to be stable and Postgres's top-N
# sort on a small result happens to be. The total order is the defence; nothing can distinguish it from
# its absence, so this comment stands in for the test that cannot exist.
async def list_by_user_filtered(
    session: AsyncSession,
    user_id: int,
    member_ids: list[int],
    *,
    search: str | None = None,
    category: ExpenseCategory | None = None,
    payment_method: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[ExpenseListRow], int]:
    private = _apply_list_filters(
        select(
            literal(SCOPE_PRIVATE).label("scope"),
            ExpenseEntry.id.label("id"),
            ExpenseEntry.date.label("date"),
            ExpenseEntry.amount.label("amount"),
            ExpenseEntry.currency.label("currency"),
            ExpenseEntry.category.label("category"),
            ExpenseEntry.notes.label("notes"),
            ExpenseEntry.payment_method.label("payment_method"),
            ExpenseEntry.credit_card_id.label("credit_card_id"),
            ExpenseEntry.account_id.label("account_id"),
            ExpenseEntry.source.label("source"),
            ExpenseEntry.payment_obligation_id.label("payment_obligation_id"),
            ExpenseEntry.subscription_id.label("subscription_id"),
            ExpenseEntry.installment_id.label("installment_id"),
            ExpenseEntry.reconciliation_id.label("reconciliation_id"),
            ExpenseEntry.account_reconciliation_id.label("account_reconciliation_id"),
            ExpenseEntry.created_at.label("created_at"),
            ExpenseEntry.updated_at.label("updated_at"),
            null().label("group_id"),
            null().label("full_amount"),
        ).where(ExpenseEntry.user_id == user_id),
        ExpenseEntry,
        search=search,
        category=category,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
    )

    if member_ids:
        shared = _apply_list_filters(
            select(
                literal(SCOPE_SHARED).label("scope"),
                SharedExpense.id.label("id"),
                SharedExpense.date.label("date"),
                SharedExpenseSplit.amount.label("amount"),
                SharedExpense.currency.label("currency"),
                SharedExpense.category.label("category"),
                SharedExpense.notes.label("notes"),
                SharedExpense.payment_method.label("payment_method"),
                null().label("credit_card_id"),
                null().label("account_id"),
                literal(SOURCE_SHARED).label("source"),
                null().label("payment_obligation_id"),
                null().label("subscription_id"),
                null().label("installment_id"),
                null().label("reconciliation_id"),
                null().label("account_reconciliation_id"),
                SharedExpense.created_at.label("created_at"),
                SharedExpense.updated_at.label("updated_at"),
                SharedExpense.group_id.label("group_id"),
                SharedExpense.amount.label("full_amount"),
            )
            .join(SharedExpense, SharedExpense.id == SharedExpenseSplit.shared_expense_id)
            # A split of zero is a payer who took no part in the expense (legal, per D33). It is not
            # spending, so it does not belong in a spending list.
            .where(SharedExpenseSplit.member_id.in_(member_ids), SharedExpenseSplit.amount > 0),
            SharedExpense,
            search=search,
            category=category,
            payment_method=payment_method,
            date_from=date_from,
            date_to=date_to,
        )
        rows = union_all(private, shared).subquery()
    else:
        rows = private.subquery()

    count_result = await session.execute(select(func.count()).select_from(rows))
    total = count_result.scalar_one()

    query = apply_entry_sort(
        select(rows),
        sort_by,
        sort_order,
        sort_columns=sort_columns(rows),
        default_order=(rows.c.date.desc(), rows.c.id.desc(), rows.c.scope),
        tie_break=(rows.c.id.desc(), rows.c.scope),
    )
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    return [ExpenseListRow(*row) for row in result.all()], total


# Get a single expense by id and user_id.
async def get_by_id(session: AsyncSession, expense_id: int, user_id: int) -> ExpenseEntry | None:
    result = await session.execute(select(ExpenseEntry).where(ExpenseEntry.id == expense_id, ExpenseEntry.user_id == user_id))
    return result.scalar_one_or_none()


# Returns whether the user has any expense entry (cheap existence check for onboarding).
async def exists_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(ExpenseEntry.id).where(ExpenseEntry.user_id == user_id).limit(1))
    return result.first() is not None


# Returns whether any expense links this account (used to lock the account's currency once linked).
async def exists_by_account_id(session: AsyncSession, account_id: int, user_id: int) -> bool:
    result = await session.execute(select(ExpenseEntry.id).where(ExpenseEntry.account_id == account_id, ExpenseEntry.user_id == user_id).limit(1))
    return result.first() is not None


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
async def count_by_credit_card(session: AsyncSession, credit_card_id: int, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(
            ExpenseEntry.credit_card_id == credit_card_id,
            ExpenseEntry.user_id == user_id,
        )
    )
    return int(result.scalar_one())


# Count expenses grouped by credit card id. Returns {card_id: count}.
async def count_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int], user_id: int) -> dict[int, int]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            func.count(),
        )
        .where(
            ExpenseEntry.credit_card_id.in_(credit_card_ids),
            ExpenseEntry.user_id == user_id,
        )
        .group_by(ExpenseEntry.credit_card_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Sum of expenses linked to each account, grouped by account_id. Returns {account_id: total}.
# Every linked row is in the account's currency (enforced at link time), so no currency split.
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
        select(ExpenseEntry.account_id, func.coalesce(func.sum(ExpenseEntry.amount), 0))
        .join(Account, Account.id == ExpenseEntry.account_id)
        .where(ExpenseEntry.account_id.in_(account_ids), ExpenseEntry.user_id == user_id, ExpenseEntry.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(ExpenseEntry.date <= as_of_date)
    result = await session.execute(stmt.group_by(ExpenseEntry.account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Expense totals linked to each account, grouped by (account_id, date), for a caller deriving those
# accounts' balances at MANY dates in one pass. Same bounds as the point-in-time sum — see the note
# on income_repository.sum_by_account_ids_dated, which this mirrors term for term.
async def sum_by_account_ids_dated(
    session: AsyncSession, account_ids: list[int], user_id: int | None, *, until: date_type
) -> list[tuple[int, date_type, Decimal]]:
    if not account_ids:
        return []
    result = await session.execute(
        select(ExpenseEntry.account_id, ExpenseEntry.date, func.coalesce(func.sum(ExpenseEntry.amount), 0))
        .join(Account, Account.id == ExpenseEntry.account_id)
        .where(
            ExpenseEntry.account_id.in_(account_ids),
            ExpenseEntry.user_id == user_id,
            ExpenseEntry.date >= Account.opening_date,
            ExpenseEntry.date <= until,
        )
        .group_by(ExpenseEntry.account_id, ExpenseEntry.date)
    )
    return [(row[0], row[1], Decimal(str(row[2]))) for row in result.all()]


# Monthly expense totals linked to each account, grouped by account_id, year, month (the account's
# currency is fixed, so no currency dimension). Returns a list of (account_id, year, month, total).
async def sum_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    if not account_ids:
        return []
    year_col = func.extract("year", ExpenseEntry.date).label("year")
    month_col = func.extract("month", ExpenseEntry.date).label("month")
    result = await session.execute(
        select(ExpenseEntry.account_id, year_col, month_col, func.coalesce(func.sum(ExpenseEntry.amount), 0))
        .join(Account, Account.id == ExpenseEntry.account_id)
        .where(ExpenseEntry.account_id.in_(account_ids), ExpenseEntry.user_id == user_id, ExpenseEntry.date >= Account.opening_date)
        .group_by(ExpenseEntry.account_id, year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), Decimal(str(row[3]))) for row in result.all()]


# Sum of expenses grouped by credit card id and currency. Returns {card_id: {currency: total}}.
async def sum_by_credit_card_ids_grouped(
    session: AsyncSession,
    credit_card_ids: list[int],
    user_id: int,
) -> dict[int, dict[str, float]]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            ExpenseEntry.credit_card_id,
            ExpenseEntry.currency,
            func.coalesce(func.sum(ExpenseEntry.amount), 0),
        )
        .where(
            ExpenseEntry.credit_card_id.in_(credit_card_ids),
            ExpenseEntry.user_id == user_id,
        )
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
    user_id: int,
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
        .where(
            ExpenseEntry.credit_card_id.in_(credit_card_ids),
            ExpenseEntry.user_id == user_id,
        )
        .group_by(ExpenseEntry.credit_card_id, year_col, month_col, ExpenseEntry.currency)
        .order_by(year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], float(row[4])) for row in result.all()]


# Monthly expense totals for a user grouped by currency.
# Returns a list of (year, month, currency, total) tuples.
async def sum_by_user_monthly(
    session: AsyncSession,
    user_id: int,
    member_ids: list[int],
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[int, int, str, Decimal]]:
    rows = _spending_rows(user_id, member_ids, date_from=date_from, date_to=date_to)
    stmt = (
        select(rows.c.year, rows.c.month, rows.c.currency, func.coalesce(func.sum(rows.c.amount), 0))
        .group_by(rows.c.year, rows.c.month, rows.c.currency)
        .order_by(rows.c.year, rows.c.month)
    )
    result = await session.execute(stmt)
    return [(int(row[0]), int(row[1]), row[2], row[3]) for row in result.all()]


# Expense totals grouped by category for a user within a date range. NULL categories are
# coalesced into the synthetic key 'uncategorized' so the breakdown covers every row
# (the column is a native PG enum, so the coalesce happens in the row mapper, not SQL).
# Returns a list of (category, currency, total) tuples.
async def sum_by_user_grouped_by_category(
    session: AsyncSession,
    user_id: int,
    member_ids: list[int],
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[str, str, Decimal]]:
    rows = _spending_rows(user_id, member_ids, date_from=date_from, date_to=date_to)
    stmt = select(rows.c.category, rows.c.currency, func.coalesce(func.sum(rows.c.amount), 0)).group_by(rows.c.category, rows.c.currency)
    result = await session.execute(stmt)
    return [("uncategorized" if row[0] is None else str(row[0]), row[1], row[2]) for row in result.all()]


# Every row that counts as this person's spending in a window: their own expenses, plus their SHARE of
# every shared expense they are in — the same union /expenses lists, reduced to the four columns the
# aggregates above group on.
#
# It exists because the dashboard was summing one of those two and the list page was showing both, so
# the totals on the finance dashboard disagreed with the list they summarise. D2 settles which figure
# is the person's: their share, never the whole bill. A split of zero is a payer who took no part, which
# is legal and is not spending, so it is excluded exactly as the list excludes it.
#
# The shared branch is not built at all for a user in no group — which is every solo user, on the app's
# most-used aggregate — and the caller's seats are resolved BEFORE the query rather than joined inside
# it, for the reason §21 measured: the join makes Postgres scan every split in the database.
#
# ▸ TWO PROPERTIES HERE ARE NOT OBSERVABLE, and a mutation sweep proved both rather than leaving them
# implied. The early return is a PERFORMANCE decision: `member_id IN ()` matches nothing, so deleting it
# returns identical rows and only costs the plan. And `amount > 0` cannot be seen through a SUM at all,
# because a zero share contributes zero either way — it earns its place by keeping this predicate
# identical to the one /expenses lists rows under, and its income-side twin IS observable, through the
# MIN(date) the liquidity card reads.
def _spending_rows(user_id: int, member_ids: list[int], *, date_from: date_type | None, date_to: date_type | None):
    private = select(
        func.extract("year", ExpenseEntry.date).label("year"),
        func.extract("month", ExpenseEntry.date).label("month"),
        ExpenseEntry.currency.label("currency"),
        cast(ExpenseEntry.category, String).label("category"),
        ExpenseEntry.amount.label("amount"),
    ).where(ExpenseEntry.user_id == user_id)
    if date_from is not None:
        private = private.where(ExpenseEntry.date >= date_from)
    if date_to is not None:
        private = private.where(ExpenseEntry.date <= date_to)
    if not member_ids:
        return private.subquery()

    shared = (
        select(
            func.extract("year", SharedExpense.date).label("year"),
            func.extract("month", SharedExpense.date).label("month"),
            SharedExpense.currency.label("currency"),
            cast(SharedExpense.category, String).label("category"),
            SharedExpenseSplit.amount.label("amount"),
        )
        .join(SharedExpense, SharedExpense.id == SharedExpenseSplit.shared_expense_id)
        .where(SharedExpenseSplit.member_id.in_(member_ids), SharedExpenseSplit.amount > 0)
    )
    if date_from is not None:
        shared = shared.where(SharedExpense.date >= date_from)
    if date_to is not None:
        shared = shared.where(SharedExpense.date <= date_to)
    return union_all(private, shared).subquery()


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


# Returns {subscription_id: [ExpenseEntry, ...]} for ALL expenses linked to any of the
# given subscriptions, sorted by date DESC (newest first). The Payments Calendar pairs
# past cycles against the full linked history (each expense bound to its closest cycle),
# so no date-window restriction — mirror of list_linked_obligation_expenses.
async def list_linked_subscription_expenses(
    session: AsyncSession,
    user_id: int,
    subscription_ids: list[int],
) -> dict[int, list[ExpenseEntry]]:
    if not subscription_ids:
        return {}
    stmt = (
        select(ExpenseEntry)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.subscription_id.in_(subscription_ids))
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
    )
    result = await session.execute(stmt)
    grouped: dict[int, list[ExpenseEntry]] = {}
    for entry in result.scalars().all():
        assert entry.subscription_id is not None  # filtered by WHERE clause.
        grouped.setdefault(entry.subscription_id, []).append(entry)
    return grouped


# Same shape for installments: {installment_id: [ExpenseEntry, ...]} sorted DESC by date.
async def list_linked_installment_expenses(
    session: AsyncSession,
    user_id: int,
    installment_ids: list[int],
) -> dict[int, list[ExpenseEntry]]:
    if not installment_ids:
        return {}
    stmt = (
        select(ExpenseEntry)
        .where(ExpenseEntry.user_id == user_id)
        .where(ExpenseEntry.installment_id.in_(installment_ids))
        .order_by(ExpenseEntry.date.desc(), ExpenseEntry.id.desc())
    )
    result = await session.execute(stmt)
    grouped: dict[int, list[ExpenseEntry]] = {}
    for entry in result.scalars().all():
        assert entry.installment_id is not None  # filtered by WHERE clause.
        grouped.setdefault(entry.installment_id, []).append(entry)
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


# Which of the given accounts have any linked expense row at all. Drives the currency lock, so unlike
# sum_by_account_ids it is NOT bounded by opening_date: a pre-opening row contributes nothing to the
# balance but is still denominated in the account's currency.
async def linked_account_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(ExpenseEntry.account_id)
        .where(ExpenseEntry.account_id.in_(account_ids), ExpenseEntry.user_id == user_id)
        .group_by(ExpenseEntry.account_id)
    )
    return {row[0] for row in result.all()}


# Namespace to call repository functions (e.g. expense_repository.list_by_user_filtered).
class ExpenseRepository:
    bulk_create = staticmethod(bulk_create)
    count_by_credit_card = staticmethod(count_by_credit_card)
    count_by_credit_card_ids = staticmethod(count_by_credit_card_ids)
    create = staticmethod(create)
    delete = staticmethod(delete)
    exists_by_account_id = staticmethod(exists_by_account_id)
    linked_account_ids = staticmethod(linked_account_ids)
    exists_by_user = staticmethod(exists_by_user)
    find_auto_charge_match = staticmethod(find_auto_charge_match)
    get_by_id = staticmethod(get_by_id)
    is_most_recent_linked_installment_expense = staticmethod(is_most_recent_linked_installment_expense)
    is_most_recent_linked_obligation_expense = staticmethod(is_most_recent_linked_obligation_expense)
    is_most_recent_linked_subscription_expense = staticmethod(is_most_recent_linked_subscription_expense)
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    list_dedup_keys_by_user = staticmethod(list_dedup_keys_by_user)
    list_linked_installment_expenses = staticmethod(list_linked_installment_expenses)
    list_linked_obligation_expenses = staticmethod(list_linked_obligation_expenses)
    list_linked_subscription_expenses = staticmethod(list_linked_subscription_expenses)
    max_linked_obligation_dates = staticmethod(max_linked_obligation_dates)
    save = staticmethod(save)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_dated = staticmethod(sum_by_account_ids_dated)
    sum_by_account_ids_monthly = staticmethod(sum_by_account_ids_monthly)
    sum_by_credit_card_ids_grouped = staticmethod(sum_by_credit_card_ids_grouped)
    sum_by_credit_card_ids_monthly = staticmethod(sum_by_credit_card_ids_monthly)
    sum_by_user_grouped_by_category = staticmethod(sum_by_user_grouped_by_category)
    sum_by_user_monthly = staticmethod(sum_by_user_monthly)


# Singleton used by services to access expense persistence.
expense_repository = ExpenseRepository()
