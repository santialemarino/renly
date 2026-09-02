# Data access for shared income and the two-sided splits under it.
#
# Like shared_expense_repository, and unlike every owner-scoped repository here, these queries are NOT
# filtered by user_id: the rows belong to the GROUP, and the membership RLS policy is what scopes them
# to the requesting user. A lookup returning None therefore means "does not exist" OR "not visible to
# you", indistinguishable by design, and the service maps both to NotFoundError.
#
# The account sums carry no user filter for a second reason as well: a shared account's balance must
# not depend on who is asking, so every reader who can see the account sums the same rows.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.shared_income import SharedIncome, SharedIncomeSplit


# Lists a group's shared income, newest first. Unpaginated on purpose, matching the expense sibling:
# the group hub shows the group's own activity, and a group's row count is bounded by what a household
# records rather than by a whole user's history — the paginated view of the same rows is the /income
# union.
async def list_by_group(session: AsyncSession, group_id: int) -> list[SharedIncome]:
    result = await session.execute(
        select(SharedIncome).where(SharedIncome.group_id == group_id).order_by(SharedIncome.date.desc(), SharedIncome.id.desc())
    )
    return list(result.scalars().all())


# Fetches one piece of shared income by id. Scoped by RLS rather than by an owner filter — the row
# belongs to the group, so "may I see it" is the membership policy's answer, not this query's.
async def get_by_id(session: AsyncSession, income_id: int) -> SharedIncome | None:
    result = await session.execute(select(SharedIncome).where(SharedIncome.id == income_id))
    return result.scalar_one_or_none()


# Every split of the given income rows, keyed by income id. The batch sibling of a per-row read,
# because a list of income always needs all of its splits at once.
async def list_splits_by_income_ids(session: AsyncSession, income_ids: list[int]) -> dict[int, list[SharedIncomeSplit]]:
    if not income_ids:
        return {}
    result = await session.execute(
        select(SharedIncomeSplit).where(SharedIncomeSplit.shared_income_id.in_(income_ids)).order_by(SharedIncomeSplit.member_id)
    )
    by_income: dict[int, list[SharedIncomeSplit]] = {}
    for split in result.scalars().all():
        by_income.setdefault(split.shared_income_id, []).append(split)
    return by_income


# Each member's two sides of everything the given groups have earned, aggregated per currency:
# (group_id, currency, member_id, Σ entitled, Σ received). The input to the balance derivation, and
# `amount` comes FIRST exactly as it does in the expense sibling so the two aggregates read alike —
# domain.shared_flow.income_positions is what knows which of the two is a claim and which is a credit.
#
# Aggregated in SQL rather than by loading every split, because a group's balance does not depend on
# which income produced it — only on the two totals per member per bucket.
#
# Batched over groups because the guard that runs before an account is deleted has to answer the
# question for every group the leaver sits in, and asking per group inside a loop is the N+1 this
# avoids. A single group is this with a one-element list.
async def list_positions_by_groups(session: AsyncSession, group_ids: list[int]) -> list[tuple[int, str, int, Decimal, Decimal]]:
    if not group_ids:
        return []
    result = await session.execute(
        select(
            SharedIncome.group_id,
            SharedIncome.currency,
            SharedIncomeSplit.member_id,
            func.coalesce(func.sum(SharedIncomeSplit.amount), 0),
            func.coalesce(func.sum(SharedIncomeSplit.received_amount), 0),
        )
        .join(SharedIncome, SharedIncome.id == SharedIncomeSplit.shared_income_id)
        .where(SharedIncome.group_id.in_(group_ids))
        .group_by(SharedIncome.group_id, SharedIncome.currency, SharedIncomeSplit.member_id)
    )
    return [(row[0], row[1], row[2], Decimal(str(row[3])), Decimal(str(row[4]))) for row in result.all()]


# Inserts a shared-income row and flushes so its id is available for the splits.
async def create(session: AsyncSession, income: SharedIncome) -> SharedIncome:
    session.add(income)
    await session.flush()
    return income


# Inserts every split of one income row in one statement.
async def create_splits(session: AsyncSession, splits: list[SharedIncomeSplit]) -> list[SharedIncomeSplit]:
    if not splits:
        return []
    session.add_all(splits)
    await session.flush()
    return splits


# Stages a shared-income row for update (caller commits).
async def save(session: AsyncSession, income: SharedIncome) -> None:
    session.add(income)


# Deletes a shared-income row. Its splits go with it through the FK's ON DELETE CASCADE — which is what
# the edit path relies on too, since re-splitting replaces every row rather than reconciling them.
async def delete(session: AsyncSession, income: SharedIncome) -> None:
    await session.delete(income)


# Deletes every split of one income row, so a re-split writes a whole new set rather than trying to
# match rows up. A member dropped from the split has to lose their row, and a diff that missed one
# would leave a stale share summing the income to more than its total.
async def delete_splits(session: AsyncSession, income_id: int) -> None:
    splits = await session.execute(select(SharedIncomeSplit).where(SharedIncomeSplit.shared_income_id == income_id))
    for split in splits.scalars().all():
        await session.delete(split)


# Shared-income totals that arrived in each account, grouped by account_id. Returns {account_id: total}.
#
# The account's balance rises by the WHOLE amount, not by anyone's share: the money really arrived in
# that account. Who owes whom afterwards is the splits' business and never the account's — the exact
# mirror of the expense sum, which subtracts the whole expense however it divided.
# Bounded below by the account's own opening_date for the same reason every other leg of the union is —
# opening_balance IS the balance at that date, so an earlier row is already inside it.
async def sum_by_account_ids(session: AsyncSession, account_ids: list[int], *, as_of_date: date_type | None = None) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = (
        select(SharedIncome.paid_to_account_id, func.coalesce(func.sum(SharedIncome.amount), 0))
        .join(Account, Account.id == SharedIncome.paid_to_account_id)
        .where(SharedIncome.paid_to_account_id.in_(account_ids), SharedIncome.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(SharedIncome.date <= as_of_date)
    result = await session.execute(stmt.group_by(SharedIncome.paid_to_account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# The same totals grouped by (account_id, date), for a caller deriving balances at many dates in one
# pass. Mirrors shared_expense_repository.sum_by_account_ids_dated term for term.
async def sum_by_account_ids_dated(session: AsyncSession, account_ids: list[int], *, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    if not account_ids:
        return []
    result = await session.execute(
        select(SharedIncome.paid_to_account_id, SharedIncome.date, func.coalesce(func.sum(SharedIncome.amount), 0))
        .join(Account, Account.id == SharedIncome.paid_to_account_id)
        .where(
            SharedIncome.paid_to_account_id.in_(account_ids),
            SharedIncome.date >= Account.opening_date,
            SharedIncome.date <= until,
        )
        .group_by(SharedIncome.paid_to_account_id, SharedIncome.date)
    )
    return [(row[0], row[1], Decimal(str(row[2]))) for row in result.all()]


# Which of the given accounts any shared income has arrived in. Feeds the currency lock, exactly as the
# private income version does: an account a group's income has landed in is denominated, and
# re-denominating it would silently restate what arrived.
async def linked_account_ids(session: AsyncSession, account_ids: list[int]) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(select(SharedIncome.paid_to_account_id).where(SharedIncome.paid_to_account_id.in_(account_ids)).distinct())
    return {row[0] for row in result.all()}


# Namespace to call repository functions (e.g. shared_income_repository.list_by_group).
class SharedIncomeRepository:
    create = staticmethod(create)
    create_splits = staticmethod(create_splits)
    delete = staticmethod(delete)
    delete_splits = staticmethod(delete_splits)
    get_by_id = staticmethod(get_by_id)
    linked_account_ids = staticmethod(linked_account_ids)
    list_by_group = staticmethod(list_by_group)
    list_positions_by_groups = staticmethod(list_positions_by_groups)
    list_splits_by_income_ids = staticmethod(list_splits_by_income_ids)
    save = staticmethod(save)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_dated = staticmethod(sum_by_account_ids_dated)


# Singleton used by services to access shared-income persistence.
shared_income_repository = SharedIncomeRepository()
