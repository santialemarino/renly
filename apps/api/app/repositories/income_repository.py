from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import String, cast, func, literal, null, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.shared_income import SharedIncome, SharedIncomeSplit
from app.repositories.utils import apply_entry_sort

# The two things a row in the unioned income list can be. A private income_entries row of the caller's
# own, or the caller's SHARE of income their group recorded.
SCOPE_PRIVATE = "private"
SCOPE_SHARED = "shared"

# What a shared row reports as its origin. `source` means "how did this get into Renly", and for a row
# that is one member's share of a group's income there is no truer answer.
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
    }


# One row of the unioned income list, in the projection both branches produce.
#
# It is a flat projection rather than an ORM row because the two branches read different tables and
# neither is a superset of the other — hydrating each side back into its model would cost two more
# queries and hand the service two shapes to reconcile.
#
# Three fields carry the whole difference between the branches:
#   * `scope` says which table the row came from. It is also half the identity: `id` is unique within
#     each table but NOT across the union, so (scope, id) is the key and (scope, id) is the tie-break.
#   * `amount` is the caller's own figure either way — the whole entry when it is private, their
#     SHARE when it is shared, which is the one rule the flow half rests on (your share is your income).
#   * `full_amount` is the shared income's total, so a reader can say "your 40 of 100" without a second
#     request. Null on a private row, where the two would be the same number twice.
#
# `account_id` is deliberately null on a shared row. It identifies where the money LANDED, which is
# frequently another member's account or one a pot holds, and a row describing your share should not
# carry somebody else's account id.
class IncomeListRow(NamedTuple):
    scope: str
    id: int
    date: date_type
    amount: Decimal
    currency: str
    category: IncomeCategory | None
    notes: str | None
    account_id: int | None
    source: str
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
    category: IncomeCategory | None,
    date_from: date_type | None,
    date_to: date_type | None,
):
    if search:
        stmt = stmt.where(model.notes.ilike(f"%{search}%"))
    if category is not None:
        stmt = stmt.where(model.category == category)
    if date_from is not None:
        stmt = stmt.where(model.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(model.date <= date_to)
    return stmt


# Lists the caller's income: their own private rows, plus their SHARE of every piece of income their
# group seats take a share of, as one paginated, sorted, filtered list.
#
# `member_ids` are the caller's own active group seats. When it is empty the shared branch is not built
# at all and the statement is exactly the private query this function has always run — a solo user (who
# is every user at launch) pays nothing for a union with no rows in it. The filters are applied by one
# helper to each branch, so the branches cannot drift even though only one of them is always present.
#
# The seats are resolved by the caller rather than joined here for the reason the /expenses union
# measured: joining group_members to filter the splits makes Postgres scan every split in the database,
# while an `IN (seat ids)` predicate uses the splits' member index.
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
    category: IncomeCategory | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[IncomeListRow], int]:
    private = _apply_list_filters(
        select(
            literal(SCOPE_PRIVATE).label("scope"),
            IncomeEntry.id.label("id"),
            IncomeEntry.date.label("date"),
            IncomeEntry.amount.label("amount"),
            IncomeEntry.currency.label("currency"),
            IncomeEntry.category.label("category"),
            IncomeEntry.notes.label("notes"),
            IncomeEntry.account_id.label("account_id"),
            IncomeEntry.source.label("source"),
            IncomeEntry.reconciliation_id.label("reconciliation_id"),
            IncomeEntry.account_reconciliation_id.label("account_reconciliation_id"),
            IncomeEntry.created_at.label("created_at"),
            IncomeEntry.updated_at.label("updated_at"),
            null().label("group_id"),
            null().label("full_amount"),
        ).where(IncomeEntry.user_id == user_id),
        IncomeEntry,
        search=search,
        category=category,
        date_from=date_from,
        date_to=date_to,
    )

    if member_ids:
        shared = _apply_list_filters(
            select(
                literal(SCOPE_SHARED).label("scope"),
                SharedIncome.id.label("id"),
                SharedIncome.date.label("date"),
                SharedIncomeSplit.amount.label("amount"),
                SharedIncome.currency.label("currency"),
                SharedIncome.category.label("category"),
                SharedIncome.notes.label("notes"),
                null().label("account_id"),
                literal(SOURCE_SHARED).label("source"),
                null().label("reconciliation_id"),
                null().label("account_reconciliation_id"),
                SharedIncome.created_at.label("created_at"),
                SharedIncome.updated_at.label("updated_at"),
                SharedIncome.group_id.label("group_id"),
                SharedIncome.amount.label("full_amount"),
            )
            .join(SharedIncome, SharedIncome.id == SharedIncomeSplit.shared_income_id)
            # A split entitled to zero is somebody who only COLLECTED the money — a custodian taking no
            # share of it. That is not their income, so it does not belong in an income list.
            .where(SharedIncomeSplit.member_id.in_(member_ids), SharedIncomeSplit.amount > 0),
            SharedIncome,
            search=search,
            category=category,
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
    return [IncomeListRow(*row) for row in result.all()], total


# Get a single income entry by id and user_id.
async def get_by_id(session: AsyncSession, income_id: int, user_id: int) -> IncomeEntry | None:
    result = await session.execute(select(IncomeEntry).where(IncomeEntry.id == income_id, IncomeEntry.user_id == user_id))
    return result.scalar_one_or_none()


# Returns whether the user has any income entry (cheap existence check for onboarding).
async def exists_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(IncomeEntry.id).where(IncomeEntry.user_id == user_id).limit(1))
    return result.first() is not None


# Returns whether any income links this account (used to lock the account's currency once linked).
async def exists_by_account_id(session: AsyncSession, account_id: int, user_id: int) -> bool:
    result = await session.execute(select(IncomeEntry.id).where(IncomeEntry.account_id == account_id, IncomeEntry.user_id == user_id).limit(1))
    return result.first() is not None


# Returns the user's income dedup tuples (date, amount, currency, category, notes), used to flag
# duplicates on import. Column order matches INCOME_SPEC.dedup_fields.
async def list_dedup_keys_by_user(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[date_type, Decimal, str, IncomeCategory | None, str | None]]:
    result = await session.execute(
        select(
            IncomeEntry.date,
            IncomeEntry.amount,
            IncomeEntry.currency,
            IncomeEntry.category,
            IncomeEntry.notes,
        ).where(IncomeEntry.user_id == user_id)
    )
    return [(row[0], row[1], row[2], row[3], row[4]) for row in result.all()]


# Insert a new income entry.
async def create(session: AsyncSession, entry: IncomeEntry) -> IncomeEntry:
    session.add(entry)
    await session.flush()
    return entry


# Bulk-inserts new income entries and flushes to assign ids. Returns the inserted entries.
async def bulk_create(session: AsyncSession, entries: list[IncomeEntry]) -> list[IncomeEntry]:
    if not entries:
        return []
    session.add_all(entries)
    await session.flush()
    return entries


# Stage an income entry for update (caller commits).
async def save(session: AsyncSession, entry: IncomeEntry) -> None:
    session.add(entry)


# Delete an income entry.
async def delete(session: AsyncSession, entry: IncomeEntry) -> None:
    await session.delete(entry)


# Earliest income entry date for a user. Returns None when the user has no income entries.
# Used by the liquidity alert to size the income window during early app life.
async def get_first_income_date(session: AsyncSession, user_id: int, member_ids: list[int]) -> date_type | None:
    rows = _earning_rows(user_id, member_ids, date_from=None, date_to=None)
    result = await session.execute(select(func.min(rows.c.date)))
    return result.scalar_one_or_none()


# Total income for a user within a date range, grouped by currency.
async def sum_by_user(
    session: AsyncSession,
    user_id: int,
    member_ids: list[int],
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> dict[str, Decimal]:
    rows = _earning_rows(user_id, member_ids, date_from=date_from, date_to=date_to)
    result = await session.execute(select(rows.c.currency, func.coalesce(func.sum(rows.c.amount), 0)).group_by(rows.c.currency))
    return {row[0]: row[1] for row in result.all()}


# Sum of income linked to each account, grouped by account_id. Returns {account_id: total}.
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
        select(IncomeEntry.account_id, func.coalesce(func.sum(IncomeEntry.amount), 0))
        .join(Account, Account.id == IncomeEntry.account_id)
        .where(IncomeEntry.account_id.in_(account_ids), IncomeEntry.user_id == user_id, IncomeEntry.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(IncomeEntry.date <= as_of_date)
    result = await session.execute(stmt.group_by(IncomeEntry.account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Income totals linked to each account, grouped by (account_id, date), for a caller deriving those
# accounts' balances at MANY dates in one pass — a pot's value series, which would otherwise ask the
# database once per point.
#
# Carries the same opening_date lower bound and as-of upper bound as the point-in-time sum, because
# the series has to agree with the headline balance exactly and the only way to guarantee that is for
# the two to filter identically. `until` is the last date the caller will ask about.
# `user_id` is nullable for the same reason it effectively is on sum_by_account_ids: a pot's accounts
# have no owner, so the batch resolves to NULL and matches nothing — which is correct, since a shared
# account cannot carry private entries at all.
async def sum_by_account_ids_dated(
    session: AsyncSession, account_ids: list[int], user_id: int | None, *, until: date_type
) -> list[tuple[int, date_type, Decimal]]:
    if not account_ids:
        return []
    result = await session.execute(
        select(IncomeEntry.account_id, IncomeEntry.date, func.coalesce(func.sum(IncomeEntry.amount), 0))
        .join(Account, Account.id == IncomeEntry.account_id)
        .where(
            IncomeEntry.account_id.in_(account_ids),
            IncomeEntry.user_id == user_id,
            IncomeEntry.date >= Account.opening_date,
            IncomeEntry.date <= until,
        )
        .group_by(IncomeEntry.account_id, IncomeEntry.date)
    )
    return [(row[0], row[1], Decimal(str(row[2]))) for row in result.all()]


# Monthly income totals linked to each account, grouped by account_id, year, month (the account's
# currency is fixed, so no currency dimension). Returns a list of (account_id, year, month, total).
async def sum_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    if not account_ids:
        return []
    year_col = func.extract("year", IncomeEntry.date).label("year")
    month_col = func.extract("month", IncomeEntry.date).label("month")
    result = await session.execute(
        select(IncomeEntry.account_id, year_col, month_col, func.coalesce(func.sum(IncomeEntry.amount), 0))
        .join(Account, Account.id == IncomeEntry.account_id)
        .where(IncomeEntry.account_id.in_(account_ids), IncomeEntry.user_id == user_id, IncomeEntry.date >= Account.opening_date)
        .group_by(IncomeEntry.account_id, year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), Decimal(str(row[3]))) for row in result.all()]


# Monthly income totals for a user grouped by currency.
# Returns a list of (year, month, currency, total) tuples.
async def sum_by_user_monthly(
    session: AsyncSession,
    user_id: int,
    member_ids: list[int],
    *,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> list[tuple[int, int, str, Decimal]]:
    rows = _earning_rows(user_id, member_ids, date_from=date_from, date_to=date_to)
    year_col = func.extract("year", rows.c.date).label("year")
    month_col = func.extract("month", rows.c.date).label("month")
    stmt = (
        select(year_col, month_col, rows.c.currency, func.coalesce(func.sum(rows.c.amount), 0))
        .group_by(year_col, month_col, rows.c.currency)
        .order_by(year_col, month_col)
    )
    result = await session.execute(stmt)
    return [(int(row[0]), int(row[1]), row[2], row[3]) for row in result.all()]


# Income totals grouped by category for a user within a date range. NULL categories are
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
    rows = _earning_rows(user_id, member_ids, date_from=date_from, date_to=date_to)
    stmt = select(rows.c.category, rows.c.currency, func.coalesce(func.sum(rows.c.amount), 0)).group_by(rows.c.category, rows.c.currency)
    result = await session.execute(stmt)
    return [("uncategorized" if row[0] is None else str(row[0]), row[1], row[2]) for row in result.all()]


# Every row that counts as this person's income in a window: their own entries, plus what they are
# ENTITLED to out of every shared income row they are in — the same union /income lists, reduced to the
# columns the aggregates above group on.
#
# The mirror of expense_repository._spending_rows, and it exists for the same reason: the finance
# dashboard was summing one of the two tables while the list page showed both. `amount` on a split is
# the entitlement, not what has already reached the member — the entitlement is the income, and whether
# it has been handed over yet is a BALANCE, which is the shared side of net worth rather than earnings.
#
# The shared branch is not built at all for a user in no group, and the caller's seats are resolved
# before the query rather than joined inside it — see the expense sibling for the measurement.
def _earning_rows(user_id: int, member_ids: list[int], *, date_from: date_type | None, date_to: date_type | None):
    private = select(
        IncomeEntry.date.label("date"),
        IncomeEntry.currency.label("currency"),
        cast(IncomeEntry.category, String).label("category"),
        IncomeEntry.amount.label("amount"),
    ).where(IncomeEntry.user_id == user_id)
    if date_from is not None:
        private = private.where(IncomeEntry.date >= date_from)
    if date_to is not None:
        private = private.where(IncomeEntry.date <= date_to)
    if not member_ids:
        return private.subquery()

    shared = (
        select(
            SharedIncome.date.label("date"),
            SharedIncome.currency.label("currency"),
            cast(SharedIncome.category, String).label("category"),
            SharedIncomeSplit.amount.label("amount"),
        )
        .join(SharedIncome, SharedIncome.id == SharedIncomeSplit.shared_income_id)
        .where(SharedIncomeSplit.member_id.in_(member_ids), SharedIncomeSplit.amount > 0)
    )
    if date_from is not None:
        shared = shared.where(SharedIncome.date >= date_from)
    if date_to is not None:
        shared = shared.where(SharedIncome.date <= date_to)
    return union_all(private, shared).subquery()


# Which of the given accounts have any linked income row at all. Drives the currency lock, so unlike
# sum_by_account_ids it is NOT bounded by opening_date: a pre-opening row contributes nothing to the
# balance but is still denominated in the account's currency.
async def linked_account_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(IncomeEntry.account_id).where(IncomeEntry.account_id.in_(account_ids), IncomeEntry.user_id == user_id).group_by(IncomeEntry.account_id)
    )
    return {row[0] for row in result.all()}


# Namespace to call repository functions (e.g. income_repository.list_by_user_filtered).
class IncomeRepository:
    bulk_create = staticmethod(bulk_create)
    create = staticmethod(create)
    delete = staticmethod(delete)
    exists_by_account_id = staticmethod(exists_by_account_id)
    linked_account_ids = staticmethod(linked_account_ids)
    exists_by_user = staticmethod(exists_by_user)
    get_by_id = staticmethod(get_by_id)
    get_first_income_date = staticmethod(get_first_income_date)
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    list_dedup_keys_by_user = staticmethod(list_dedup_keys_by_user)
    save = staticmethod(save)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_dated = staticmethod(sum_by_account_ids_dated)
    sum_by_account_ids_monthly = staticmethod(sum_by_account_ids_monthly)
    sum_by_user = staticmethod(sum_by_user)
    sum_by_user_grouped_by_category = staticmethod(sum_by_user_grouped_by_category)
    sum_by_user_monthly = staticmethod(sum_by_user_monthly)


# Singleton used by services to access income persistence.
income_repository = IncomeRepository()
