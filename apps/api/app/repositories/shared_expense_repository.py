# Data access for shared expenses and the two-sided splits under them.
#
# Like group_repository and pot_repository, and unlike every owner-scoped repository here, these
# queries are NOT filtered by user_id: the rows belong to the GROUP, and the membership RLS policy is
# what scopes them to the requesting user. A lookup returning None therefore means "does not exist"
# OR "not visible to you", indistinguishable by design, and the service maps both to NotFoundError.
#
# The account and card sums carry no user filter for a second reason as well: a shared account's
# balance must not depend on who is asking, so every reader who can see the account sums the same rows.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.shared_expense import SharedExpense, SharedExpenseSplit


# Lists a group's shared expenses, newest first. Unpaginated on purpose: the group hub shows the
# group's own activity, and a group's expense count is bounded by what a household records rather than
# by a whole user's history — the paginated view of the same rows is the /expenses union.
async def list_by_group(session: AsyncSession, group_id: int) -> list[SharedExpense]:
    result = await session.execute(
        select(SharedExpense).where(SharedExpense.group_id == group_id).order_by(SharedExpense.date.desc(), SharedExpense.id.desc())
    )
    return list(result.scalars().all())


# Fetches one shared expense by id. Scoped by RLS rather than by an owner filter — the row belongs to
# the group, so "may I see it" is the membership policy's answer, not this query's.
async def get_by_id(session: AsyncSession, expense_id: int) -> SharedExpense | None:
    result = await session.execute(select(SharedExpense).where(SharedExpense.id == expense_id))
    return result.scalar_one_or_none()


# Every split of the given expenses, keyed by expense id. The batch sibling of a per-expense read,
# because a list of expenses always needs all of their splits at once.
async def list_splits_by_expense_ids(session: AsyncSession, expense_ids: list[int]) -> dict[int, list[SharedExpenseSplit]]:
    if not expense_ids:
        return {}
    result = await session.execute(
        select(SharedExpenseSplit).where(SharedExpenseSplit.shared_expense_id.in_(expense_ids)).order_by(SharedExpenseSplit.member_id)
    )
    by_expense: dict[int, list[SharedExpenseSplit]] = {}
    for split in result.scalars().all():
        by_expense.setdefault(split.shared_expense_id, []).append(split)
    return by_expense


# Each member's two sides of everything the given groups have spent, aggregated per currency:
# (group_id, currency, member_id, Σ consumed, Σ fronted). The input to the balance derivation.
#
# Aggregated in SQL rather than by loading every split, because a group's balance does not depend on
# which expense produced it — only on the two totals per member per bucket. A group with a thousand
# expenses costs one row per member per currency.
#
# Batched over groups because the guard that runs before an account is deleted has to answer the
# question for every group the leaver sits in, and asking per group inside a loop is the N+1 this
# avoids. A single group is this with a one-element list.
async def list_positions_by_groups(session: AsyncSession, group_ids: list[int]) -> list[tuple[int, str, int, Decimal, Decimal]]:
    if not group_ids:
        return []
    result = await session.execute(
        select(
            SharedExpense.group_id,
            SharedExpense.currency,
            SharedExpenseSplit.member_id,
            func.coalesce(func.sum(SharedExpenseSplit.amount), 0),
            func.coalesce(func.sum(SharedExpenseSplit.paid_amount), 0),
        )
        .join(SharedExpense, SharedExpense.id == SharedExpenseSplit.shared_expense_id)
        .where(SharedExpense.group_id.in_(group_ids))
        .group_by(SharedExpense.group_id, SharedExpense.currency, SharedExpenseSplit.member_id)
    )
    return [(row[0], row[1], row[2], Decimal(str(row[3])), Decimal(str(row[4]))) for row in result.all()]


# The same aggregate bucketed by MONTH, as (group_id, year, month, currency, member_id, amount,
# paid_amount) — the input the dashboard's net-worth series accumulates into a position per point.
#
# One query for the whole history rather than one per point, which is the same reason
# compute_account_balance_series exists: a twelve-month chart must not cost twelve aggregates. The
# caller accumulates forward and runs each month's totals through the SAME domain functions the live
# balance uses, so a point on the chart and the figure on the group hub cannot be computed two ways.
async def list_positions_by_groups_monthly(session: AsyncSession, group_ids: list[int]) -> list[tuple[int, int, int, str, int, Decimal, Decimal]]:
    if not group_ids:
        return []
    year_col = func.extract("year", SharedExpense.date).label("year")
    month_col = func.extract("month", SharedExpense.date).label("month")
    result = await session.execute(
        select(
            SharedExpense.group_id,
            year_col,
            month_col,
            SharedExpense.currency,
            SharedExpenseSplit.member_id,
            func.coalesce(func.sum(SharedExpenseSplit.amount), 0),
            func.coalesce(func.sum(SharedExpenseSplit.paid_amount), 0),
        )
        .join(SharedExpense, SharedExpense.id == SharedExpenseSplit.shared_expense_id)
        .where(SharedExpense.group_id.in_(group_ids))
        .group_by(SharedExpense.group_id, year_col, month_col, SharedExpense.currency, SharedExpenseSplit.member_id)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], row[4], Decimal(str(row[5])), Decimal(str(row[6]))) for row in result.all()]


# Inserts a shared expense and flushes so its id is available for the splits.
async def create(session: AsyncSession, expense: SharedExpense) -> SharedExpense:
    session.add(expense)
    await session.flush()
    return expense


# Inserts every split of one expense in one statement.
async def create_splits(session: AsyncSession, splits: list[SharedExpenseSplit]) -> list[SharedExpenseSplit]:
    if not splits:
        return []
    session.add_all(splits)
    await session.flush()
    return splits


# Stages a shared expense for update (caller commits).
async def save(session: AsyncSession, expense: SharedExpense) -> None:
    session.add(expense)


# Deletes a shared expense. Its splits go with it through the FK's ON DELETE CASCADE — which is what
# the edit path relies on too, since re-splitting replaces every row rather than reconciling them.
async def delete(session: AsyncSession, expense: SharedExpense) -> None:
    await session.delete(expense)


# Deletes every split of one expense, so a re-split writes a whole new set rather than trying to
# match rows up. A member dropped from the split has to lose their row, and a diff that missed one
# would leave a stale share summing the expense to more than its total.
async def delete_splits(session: AsyncSession, expense_id: int) -> None:
    splits = await session.execute(select(SharedExpenseSplit).where(SharedExpenseSplit.shared_expense_id == expense_id))
    for split in splits.scalars().all():
        await session.delete(split)


# Shared-expense totals drawn from each account, grouped by account_id. Returns {account_id: total}.
#
# The account's balance falls by the WHOLE expense, not by anyone's share: the money left that account.
# Who owed whom afterwards is the splits' business and never the account's.
# Bounded below by the account's own opening_date for the same reason every other leg of the union is —
# opening_balance IS the balance at that date, so an earlier row is already inside it.
async def sum_by_account_ids(session: AsyncSession, account_ids: list[int], *, as_of_date: date_type | None = None) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = (
        select(SharedExpense.paid_from_account_id, func.coalesce(func.sum(SharedExpense.amount), 0))
        .join(Account, Account.id == SharedExpense.paid_from_account_id)
        .where(SharedExpense.paid_from_account_id.in_(account_ids), SharedExpense.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(SharedExpense.date <= as_of_date)
    result = await session.execute(stmt.group_by(SharedExpense.paid_from_account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# The same totals grouped by (account_id, date), for a caller deriving balances at many dates in one
# pass. Mirrors expense_repository.sum_by_account_ids_dated term for term.
async def sum_by_account_ids_dated(session: AsyncSession, account_ids: list[int], *, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    if not account_ids:
        return []
    result = await session.execute(
        select(SharedExpense.paid_from_account_id, SharedExpense.date, func.coalesce(func.sum(SharedExpense.amount), 0))
        .join(Account, Account.id == SharedExpense.paid_from_account_id)
        .where(
            SharedExpense.paid_from_account_id.in_(account_ids),
            SharedExpense.date >= Account.opening_date,
            SharedExpense.date <= until,
        )
        .group_by(SharedExpense.paid_from_account_id, SharedExpense.date)
    )
    return [(row[0], row[1], Decimal(str(row[2]))) for row in result.all()]


# Shared-expense charges on each card as {card_id: {currency: total}} — the SAME nested shape
# expense_repository.sum_by_credit_card_ids_grouped returns, because the two are merged bucket by
# bucket before compute_card_balances sees them. A card's liability is per currency bucket and a
# group's expense can be in any of them, including one the card has never seen before.
async def sum_by_credit_card_ids_grouped(session: AsyncSession, card_ids: list[int]) -> dict[int, dict[str, float]]:
    if not card_ids:
        return {}
    result = await session.execute(
        select(SharedExpense.credit_card_id, SharedExpense.currency, func.coalesce(func.sum(SharedExpense.amount), 0))
        .where(SharedExpense.credit_card_id.in_(card_ids))
        .group_by(SharedExpense.credit_card_id, SharedExpense.currency)
    )
    grouped: dict[int, dict[str, float]] = {}
    for card_id, currency, total in result.all():
        grouped.setdefault(card_id, {})[currency] = total
    return grouped


# The same charges bucketed by MONTH, as (card_id, year, month, currency, total) — the monthly sibling
# of sum_by_credit_card_ids_grouped, matching what expense_repository returns for private rows.
#
# It exists because get_card_balances merges both tables for the CURRENT balance while the evolution
# chart's monthly card series read only the private one, so the headline card figure and the chart's
# card line described different sets of charges. A card's whole charge is its owner's liability
# whoever consumed what it bought, which is why there is no split here and no user filter: the rows
# belong to the group, RLS scopes them, and a card only ever carries its own owner's charges.
async def sum_by_credit_card_ids_monthly(session: AsyncSession, card_ids: list[int]) -> list[tuple[int, int, int, str, float]]:
    if not card_ids:
        return []
    year_col = func.extract("year", SharedExpense.date).label("year")
    month_col = func.extract("month", SharedExpense.date).label("month")
    result = await session.execute(
        select(
            SharedExpense.credit_card_id,
            year_col,
            month_col,
            SharedExpense.currency,
            func.coalesce(func.sum(SharedExpense.amount), 0),
        )
        .where(SharedExpense.credit_card_id.in_(card_ids))
        .group_by(SharedExpense.credit_card_id, year_col, month_col, SharedExpense.currency)
        .order_by(year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], float(row[4])) for row in result.all()]


# Counts the shared expenses charged to one card, for the card-delete guard. No user filter: RLS
# already limits the rows to groups the caller is in, and a card only ever carries its owner's charges.
async def count_by_credit_card(session: AsyncSession, credit_card_id: int) -> int:
    result = await session.execute(select(func.count()).where(SharedExpense.credit_card_id == credit_card_id))
    return int(result.scalar_one())


# Which of the given accounts any shared expense draws from. Feeds the currency lock, exactly as the
# private expense version does: an account a group has spent from is denominated, and re-denominating
# it would silently restate what left it.
async def linked_account_ids(session: AsyncSession, account_ids: list[int]) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(select(SharedExpense.paid_from_account_id).where(SharedExpense.paid_from_account_id.in_(account_ids)).distinct())
    return {row[0] for row in result.all()}


# Namespace to call repository functions (e.g. shared_expense_repository.list_by_group).
class SharedExpenseRepository:
    count_by_credit_card = staticmethod(count_by_credit_card)
    create = staticmethod(create)
    create_splits = staticmethod(create_splits)
    delete = staticmethod(delete)
    delete_splits = staticmethod(delete_splits)
    get_by_id = staticmethod(get_by_id)
    linked_account_ids = staticmethod(linked_account_ids)
    list_by_group = staticmethod(list_by_group)
    list_positions_by_groups = staticmethod(list_positions_by_groups)
    list_positions_by_groups_monthly = staticmethod(list_positions_by_groups_monthly)
    list_splits_by_expense_ids = staticmethod(list_splits_by_expense_ids)
    save = staticmethod(save)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_dated = staticmethod(sum_by_account_ids_dated)
    sum_by_credit_card_ids_grouped = staticmethod(sum_by_credit_card_ids_grouped)
    sum_by_credit_card_ids_monthly = staticmethod(sum_by_credit_card_ids_monthly)


# Singleton used by services to access shared-expense persistence.
shared_expense_repository = SharedExpenseRepository()
