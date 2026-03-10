from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.investment_group import InvestmentGroup
from app.models.user import User
from app.repositories import group_repository, investment_repository


# Lists groups for the user. Returns each group with its investment ids.
async def list_groups(session: AsyncSession, user: User) -> list[tuple[InvestmentGroup, list[int]]]:
    groups = await group_repository.list_by_user(session, user.id)
    out = []
    for g in groups:
        ids = await group_repository.get_investment_ids_by_group(session, g.id)
        out.append((g, ids))
    return out


# Fetches one group by id. Raises NotFoundError if not found or not owned by user.
async def get_group(
    session: AsyncSession,
    group_id: int,
    user: User,
) -> tuple[InvestmentGroup, list[int]]:
    group = await group_repository.get_by_id(session, group_id, user.id)
    if group is None:
        raise NotFoundError("Group not found")
    ids = await group_repository.get_investment_ids_by_group(session, group.id)
    return (group, ids)


# Creates a new group for the user.
async def create_group(
    session: AsyncSession,
    user: User,
    name: str,
) -> InvestmentGroup:
    group = InvestmentGroup(user_id=user.id, name=name)
    return await group_repository.create(session, group)


# Updates an existing group. Only provided fields are updated.
async def update_group(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    name: str | None = None,
) -> tuple[InvestmentGroup, list[int]]:
    group = await group_repository.get_by_id(session, group_id, user.id)
    if group is None:
        raise NotFoundError("Group not found")
    if name is not None:
        group.name = name
        await group_repository.save(session, group)
        await session.refresh(group)
    ids = await group_repository.get_investment_ids_by_group(session, group.id)
    return (group, ids)


# Deletes a group. Raises NotFoundError if not found or not owned.
async def delete_group(
    session: AsyncSession,
    group_id: int,
    user: User,
) -> None:
    group = await group_repository.get_by_id(session, group_id, user.id)
    if group is None:
        raise NotFoundError("Group not found")
    await group_repository.delete(session, group)


# Replaces group membership with the given investment ids. All investments must belong to the user.
async def set_group_investments(
    session: AsyncSession,
    group_id: int,
    user: User,
    investment_ids: list[int],
) -> None:
    group = await group_repository.get_by_id(session, group_id, user.id)
    if group is None:
        raise NotFoundError("Group not found")
    for inv_id in investment_ids:
        inv = await investment_repository.get_by_id(session, inv_id, user.id)
        if inv is None:
            raise NotFoundError(f"Investment {inv_id} not found")
    await group_repository.set_members(session, group_id, investment_ids)
