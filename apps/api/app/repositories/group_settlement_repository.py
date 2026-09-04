# Data access for the settlements that clear a group's balances.
#
# Like group_repository and shared_expense_repository, these queries carry NO user filter: a settlement
# belongs to the group, and the membership RLS policy is what scopes it. A lookup returning None means
# "does not exist" or "not visible to you" indistinguishably, and the service maps both to NotFoundError.
#
# The two cash legs read `coalesce(<leg>_amount, amount)`, exactly as card_settlements reads its account
# leg: the leg amount is set only when the settlement crossed currencies, so NULL means "what left the
# account is what cleared the bucket". Reading `amount` on both legs would credit a cross-currency
# settlement with the other side's figure.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.group_settlement import GroupSettlement, GroupSettlementStatus

# Every status whose amount moves a balance. All of them, today — a pending settlement counts because
# the money really moved, and confirming it is an acknowledgement rather than a gate on arithmetic;
# a write-off clears the bucket without money, which is the whole point of it. Named rather than
# omitted so a later status that must NOT count has one place to be excluded from.
COUNTING_STATUSES = (GroupSettlementStatus.pending, GroupSettlementStatus.confirmed, GroupSettlementStatus.written_off)

# The statuses whose money actually left and arrived somewhere.
#
# A write-off moved nothing, and it CANNOT carry an account leg: `group_settlements_write_off_moves_nothing`
# refuses the row outright (verified against a real database), the service never writes one, and set_leg
# refuses to attach one. So this filter is unreachable by construction and no test can distinguish it
# from its absence — a mutation sweep proved exactly that, and the honest thing is to say so here rather
# than leave a comment implying coverage.
#
# It stays because it is a filter on MEANING rather than on today's constraints: these sums are "money
# that moved", and a sum that is correct only because a CHECK elsewhere holds is a sum that breaks when
# that CHECK moves. It costs one indexed predicate.
_CASH_STATUSES = (GroupSettlementStatus.pending, GroupSettlementStatus.confirmed)


# Lists a group's settlements, newest first.
async def list_by_group(session: AsyncSession, group_id: int) -> list[GroupSettlement]:
    result = await session.execute(
        select(GroupSettlement).where(GroupSettlement.group_id == group_id).order_by(GroupSettlement.date.desc(), GroupSettlement.id.desc())
    )
    return list(result.scalars().all())


# Fetches one settlement by id; RLS decides whether the caller may see it.
#
# `for_update` takes an exclusive row lock for the rest of the transaction, and every path that CHANGES
# a settlement passes it. Each of them reads the status and then acts on what it read — confirm refuses
# anything but pending, un-confirm anything but confirmed, delete refuses a confirmed row — so two of
# them running at once would both see 'pending' and one would act on a state the other had already
# left. The concrete loss is a confirmed settlement deleted out from under the payee who vouched for
# it, which is exactly the act the status is there to prevent.
#
# Locking this row rather than the group, unlike the balance-capped writes: what these need is the
# settlement not changing under them, and a group lock would serialise every settlement in the group
# against every other for no gain.
async def get_by_id(session: AsyncSession, settlement_id: int, *, for_update: bool = False) -> GroupSettlement | None:
    stmt = select(GroupSettlement).where(GroupSettlement.id == settlement_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# Every counting settlement of the given groups as (group_id, currency, from_member_id, to_member_id,
# amount) — the input the balance derivation applies on top of the expense positions.
#
# Batched over groups for the reason its expense-side sibling is: the guard before an account deletion
# asks about every group the leaver sits in at once.
async def list_movements_by_groups(session: AsyncSession, group_ids: list[int]) -> list[tuple[int, str, int, int, Decimal]]:
    if not group_ids:
        return []
    result = await session.execute(
        select(
            GroupSettlement.group_id,
            GroupSettlement.currency,
            GroupSettlement.from_member_id,
            GroupSettlement.to_member_id,
            GroupSettlement.amount,
        ).where(
            GroupSettlement.group_id.in_(group_ids),
            GroupSettlement.status.in_(COUNTING_STATUSES),
        )
    )
    return [(row[0], row[1], row[2], row[3], Decimal(str(row[4]))) for row in result.all()]


# The same movements bucketed by MONTH, as (group_id, year, month, currency, from_member_id,
# to_member_id, amount) — what the dashboard's series applies on top of each month's accumulated
# positions. `COUNTING_STATUSES` is the same filter the live read uses, so a settlement that counts on
# the group hub counts on the chart.
async def list_movements_by_groups_monthly(session: AsyncSession, group_ids: list[int]) -> list[tuple[int, int, int, str, int, int, Decimal]]:
    if not group_ids:
        return []
    year_col = func.extract("year", GroupSettlement.date).label("year")
    month_col = func.extract("month", GroupSettlement.date).label("month")
    result = await session.execute(
        select(
            GroupSettlement.group_id,
            year_col,
            month_col,
            GroupSettlement.currency,
            GroupSettlement.from_member_id,
            GroupSettlement.to_member_id,
            GroupSettlement.amount,
        ).where(
            GroupSettlement.group_id.in_(group_ids),
            GroupSettlement.status.in_(COUNTING_STATUSES),
        )
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], row[4], row[5], Decimal(str(row[6]))) for row in result.all()]


# Whether any group in the given set still has a settlement-relevant row at all. Used by the removal
# and account-deletion guards, which need to know a group has money history before computing balances.
async def group_ids_with_settlements(session: AsyncSession, group_ids: list[int]) -> set[int]:
    if not group_ids:
        return set()
    result = await session.execute(select(GroupSettlement.group_id).where(GroupSettlement.group_id.in_(group_ids)).distinct())
    return {row[0] for row in result.all()}


# Inserts a settlement.
async def create(session: AsyncSession, settlement: GroupSettlement) -> GroupSettlement:
    session.add(settlement)
    await session.flush()
    return settlement


# Persists several settlements and flushes ONCE to get their ids. The batch sibling of create, for a
# payment that spills across buckets: it writes one row per bucket, and flushing per row is a round
# trip per bucket for what is a single indivisible act. Same shape as the pot ledger's opening.
async def create_many(session: AsyncSession, settlements: list[GroupSettlement]) -> list[GroupSettlement]:
    if not settlements:
        return []
    session.add_all(settlements)
    await session.flush()
    return settlements


# Stages a settlement for update (caller commits).
async def save(session: AsyncSession, settlement: GroupSettlement) -> None:
    session.add(settlement)


# Deletes a settlement. This is what reversing one is: there is no reversed state to read back until
# the audit log exists, so the honest post-reversal state is that the payment was never recorded.
async def delete(session: AsyncSession, settlement: GroupSettlement) -> None:
    await session.delete(settlement)


# Money each account RECEIVED from a settlement, grouped by account_id. Reads the `to` leg's own figure
# when the settle crossed currencies, and the bucket amount otherwise.
async def sum_in_by_account_ids(session: AsyncSession, account_ids: list[int], *, as_of_date: date_type | None = None) -> dict[int, Decimal]:
    return await _sum_leg(session, account_ids, leg="to", as_of_date=as_of_date)


# Money each account PAID OUT through a settlement, grouped by account_id.
async def sum_out_by_account_ids(session: AsyncSession, account_ids: list[int], *, as_of_date: date_type | None = None) -> dict[int, Decimal]:
    return await _sum_leg(session, account_ids, leg="from", as_of_date=as_of_date)


# One leg's totals per account. Both legs read the SAME shape, so a change to the bounds or the
# coalesce can only ever be made to both — the failure a copy-pasted second query eventually produces.
async def _sum_leg(session: AsyncSession, account_ids: list[int], *, leg: str, as_of_date: date_type | None) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    account_column = GroupSettlement.to_account_id if leg == "to" else GroupSettlement.from_account_id
    leg_amount = GroupSettlement.to_amount if leg == "to" else GroupSettlement.from_amount
    stmt = (
        select(account_column, func.coalesce(func.sum(func.coalesce(leg_amount, GroupSettlement.amount)), 0))
        .join(Account, Account.id == account_column)
        .where(
            account_column.in_(account_ids),
            GroupSettlement.status.in_(_CASH_STATUSES),
            GroupSettlement.date >= Account.opening_date,
        )
    )
    if as_of_date is not None:
        stmt = stmt.where(GroupSettlement.date <= as_of_date)
    result = await session.execute(stmt.group_by(account_column))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# The `to` leg grouped by (account_id, date), for a caller deriving balances at many dates in one pass.
async def sum_in_by_account_ids_dated(session: AsyncSession, account_ids: list[int], *, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    return await _sum_leg_dated(session, account_ids, leg="to", until=until)


# The `from` leg grouped by (account_id, date).
async def sum_out_by_account_ids_dated(session: AsyncSession, account_ids: list[int], *, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    return await _sum_leg_dated(session, account_ids, leg="from", until=until)


# The dated form of _sum_leg, sharing its predicate for the same reason the two legs share theirs.
async def _sum_leg_dated(session: AsyncSession, account_ids: list[int], *, leg: str, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    if not account_ids:
        return []
    account_column = GroupSettlement.to_account_id if leg == "to" else GroupSettlement.from_account_id
    leg_amount = GroupSettlement.to_amount if leg == "to" else GroupSettlement.from_amount
    result = await session.execute(
        select(account_column, GroupSettlement.date, func.coalesce(func.sum(func.coalesce(leg_amount, GroupSettlement.amount)), 0))
        .join(Account, Account.id == account_column)
        .where(
            account_column.in_(account_ids),
            GroupSettlement.status.in_(_CASH_STATUSES),
            GroupSettlement.date >= Account.opening_date,
            GroupSettlement.date <= until,
        )
        .group_by(account_column, GroupSettlement.date)
    )
    return [(row[0], row[1], Decimal(str(row[2]))) for row in result.all()]


# Which of the given accounts any settlement leg touches. Feeds the currency lock: an account a
# settlement has moved money through is denominated, so re-denominating it would restate what left it.
async def linked_account_ids(session: AsyncSession, account_ids: list[int]) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(GroupSettlement.from_account_id, GroupSettlement.to_account_id).where(
            GroupSettlement.from_account_id.in_(account_ids) | GroupSettlement.to_account_id.in_(account_ids)
        )
    )
    linked: set[int] = set()
    for from_account_id, to_account_id in result.all():
        linked.update(account_id for account_id in (from_account_id, to_account_id) if account_id in set(account_ids))
    return linked


# Clears the cash legs naming an account that is being deleted, in the same transaction. Those figures
# are denominated in THAT account, so once the link is gone nothing can interpret them — and every
# reader treats "a leg amount is set" as "this settlement crossed currencies". The bucket leg survives,
# so the settlement still clears its balance exactly as before; only the cash side it can no longer
# attribute goes. Mirrors card_settlement_repository.clear_account_amounts, for the same reason.
async def clear_account_amounts(session: AsyncSession, account_id: int) -> None:
    result = await session.execute(
        select(GroupSettlement).where((GroupSettlement.from_account_id == account_id) | (GroupSettlement.to_account_id == account_id))
    )
    for settlement in result.scalars().all():
        if settlement.from_account_id == account_id:
            settlement.from_amount = None
        if settlement.to_account_id == account_id:
            settlement.to_amount = None
        session.add(settlement)


# Namespace to call repository functions (e.g. group_settlement_repository.list_by_group).
class GroupSettlementRepository:
    clear_account_amounts = staticmethod(clear_account_amounts)
    create = staticmethod(create)
    create_many = staticmethod(create_many)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    group_ids_with_settlements = staticmethod(group_ids_with_settlements)
    linked_account_ids = staticmethod(linked_account_ids)
    list_by_group = staticmethod(list_by_group)
    list_movements_by_groups = staticmethod(list_movements_by_groups)
    list_movements_by_groups_monthly = staticmethod(list_movements_by_groups_monthly)
    save = staticmethod(save)
    sum_in_by_account_ids = staticmethod(sum_in_by_account_ids)
    sum_in_by_account_ids_dated = staticmethod(sum_in_by_account_ids_dated)
    sum_out_by_account_ids = staticmethod(sum_out_by_account_ids)
    sum_out_by_account_ids_dated = staticmethod(sum_out_by_account_ids_dated)


# Singleton used by services to access settlement persistence.
group_settlement_repository = GroupSettlementRepository()
