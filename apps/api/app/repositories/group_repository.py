# Data access for investment groups and membership.

from collections import defaultdict

from sqlalchemy import asc, desc
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.investment_group import InvestmentGroup, InvestmentGroupMember

_SORT_COLUMNS = {
    "name": InvestmentGroup.name,
}


# Lists groups for a user with optional search and sorting.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> list[InvestmentGroup]:
    stmt = select(InvestmentGroup).where(InvestmentGroup.user_id == user_id)
    if search:
        stmt = stmt.where(InvestmentGroup.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else InvestmentGroup.id
    stmt = stmt.order_by(order_clause)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Fetches a single group by id and user_id. Returns None if not found or not owned.
async def get_by_id(
    session: AsyncSession,
    group_id: int,
    user_id: int,
) -> InvestmentGroup | None:
    result = await session.execute(
        select(InvestmentGroup).where(
            InvestmentGroup.id == group_id,
            InvestmentGroup.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


# Returns investment ids that belong to the group.
async def get_investment_ids_by_group(session: AsyncSession, group_id: int) -> list[int]:
    stmt = select(InvestmentGroupMember.investment_id).where(InvestmentGroupMember.group_id == group_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Returns {group_id: [investment_id, ...]} for all given group IDs in a single query.
async def get_investment_ids_by_groups(session: AsyncSession, group_ids: list[int]) -> dict[int, list[int]]:
    if not group_ids:
        return {}
    result = await session.execute(
        select(InvestmentGroupMember.group_id, InvestmentGroupMember.investment_id).where(InvestmentGroupMember.group_id.in_(group_ids))
    )
    grouped: dict[int, list[int]] = defaultdict(list)
    for row in result.all():
        grouped[row.group_id].append(row.investment_id)
    return dict(grouped)


# Persists a new group and flushes to get the id.
async def create(session: AsyncSession, group: InvestmentGroup) -> InvestmentGroup:
    session.add(group)
    await session.flush()
    return group


# Persists changes to an existing group.
async def save(session: AsyncSession, group: InvestmentGroup) -> None:
    session.add(group)


# Deletes a group. Members are removed by FK CASCADE.
async def delete(session: AsyncSession, group: InvestmentGroup) -> None:
    await session.delete(group)


# Replaces membership: delete all for group, then add (group_id, inv_id) for each id.
async def set_members(
    session: AsyncSession,
    group_id: int,
    investment_ids: list[int],
) -> None:
    await session.execute(sa_delete(InvestmentGroupMember).where(InvestmentGroupMember.group_id == group_id))
    for inv_id in investment_ids:
        session.add(InvestmentGroupMember(group_id=group_id, investment_id=inv_id))


# Replaces group membership for an investment: removes all existing, adds new group_ids.
async def set_groups_for_investment(
    session: AsyncSession,
    investment_id: int,
    group_ids: list[int],
) -> None:
    await session.execute(sa_delete(InvestmentGroupMember).where(InvestmentGroupMember.investment_id == investment_id))
    for group_id in group_ids:
        session.add(InvestmentGroupMember(investment_id=investment_id, group_id=group_id))


# Namespace to call repository functions (e.g. group_repository.list_by_user).
class GroupRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    get_investment_ids_by_group = staticmethod(get_investment_ids_by_group)
    get_investment_ids_by_groups = staticmethod(get_investment_ids_by_groups)
    list_by_user = staticmethod(list_by_user)
    save = staticmethod(save)
    set_groups_for_investment = staticmethod(set_groups_for_investment)
    set_members = staticmethod(set_members)


# Singleton used by services to access group persistence.
group_repository = GroupRepository()
