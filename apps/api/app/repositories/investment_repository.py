from sqlalchemy import asc, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.investment import Investment, InvestmentCategory
from app.models.investment_group import InvestmentGroup, InvestmentGroupMember

_SORT_COLUMNS = {
    "name": Investment.name,
    "category": Investment.category,
    "base_currency": Investment.base_currency,
    "broker": Investment.broker,
}


# Lists investments for a user with optional filters and pagination. Returns (items, total).
async def list_by_user_filtered(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    group_ids: list[int] | None = None,
    category: InvestmentCategory | None = None,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> tuple[list[Investment], int]:
    stmt = select(Investment).where(Investment.user_id == user_id)
    if active_only:
        stmt = stmt.where(Investment.is_active.is_(True))
    if search:
        stmt = stmt.where(Investment.name.ilike(f"%{search}%"))
    if category:
        stmt = stmt.where(Investment.category == category)
    if group_ids:
        stmt = stmt.where(
            Investment.id.in_(
                select(InvestmentGroupMember.investment_id).where(InvestmentGroupMember.group_id.in_(group_ids))
            )
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else Investment.id
    items_stmt = stmt.order_by(order_clause).offset((page - 1) * page_size).limit(page_size)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())
    return items, total


# Fetches a single investment by id and user_id. Returns None if not found or not owned.
async def get_by_id(
    session: AsyncSession,
    investment_id: int,
    user_id: int,
) -> Investment | None:
    result = await session.execute(
        select(Investment).where(
            Investment.id == investment_id,
            Investment.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


# Returns groups for each investment id as {investment_id: [(group_id, group_name)]}.
async def get_groups_by_investment_ids(
    session: AsyncSession,
    investment_ids: list[int],
) -> dict[int, list[tuple[int, str]]]:
    if not investment_ids:
        return {}
    stmt = (
        select(InvestmentGroupMember.investment_id, InvestmentGroup.id, InvestmentGroup.name)
        .join(InvestmentGroup, InvestmentGroupMember.group_id == InvestmentGroup.id)
        .where(InvestmentGroupMember.investment_id.in_(investment_ids))
        .order_by(InvestmentGroup.id)
    )
    result = await session.execute(stmt)
    groups_map: dict[int, list[tuple[int, str]]] = {}
    for inv_id, group_id, group_name in result.all():
        groups_map.setdefault(inv_id, []).append((group_id, group_name))
    return groups_map


# Persists investment, commits, refreshes, and returns it (with id set).
async def create(session: AsyncSession, investment: Investment) -> Investment:
    session.add(investment)
    await session.commit()
    await session.refresh(investment)
    return investment


# Persists changes to an existing investment.
async def save(session: AsyncSession, investment: Investment) -> None:
    session.add(investment)
    await session.commit()


# Returns all active investments that have a ticker set.
async def list_with_ticker(session: AsyncSession) -> list[Investment]:
    result = await session.execute(
        select(Investment).where(
            Investment.is_active == True,  # noqa: E712
            Investment.ticker.is_not(None),
        )
    )
    return list(result.scalars().all())


# Namespace to call repository functions (e.g. investment_repository.list_by_user_filtered).
class InvestmentRepository:
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    get_by_id = staticmethod(get_by_id)
    get_groups_by_investment_ids = staticmethod(get_groups_by_investment_ids)
    create = staticmethod(create)
    save = staticmethod(save)
    list_with_ticker = staticmethod(list_with_ticker)


# Singleton used by services to access investment persistence.
investment_repository = InvestmentRepository()
