from sqlalchemy import asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.installment import Installment

_SORT_COLUMNS = {
    "name": Installment.name,
    "total_amount": Installment.total_amount,
    "installment_amount": Installment.installment_amount,
    "currency": Installment.currency,
    "installments_count": Installment.installments_count,
    "current_installment": Installment.current_installment,
    "start_date": Installment.start_date,
}


# List installments for a user with optional search, sorting, and active filtering.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Installment]:
    stmt = select(Installment).where(Installment.user_id == user_id)
    if active_only:
        stmt = stmt.where(Installment.is_active.is_(True))
    if search:
        stmt = stmt.where(Installment.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else Installment.start_date.desc()
    stmt = stmt.order_by(order_clause)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single installment by id and user_id.
async def get_by_id(session: AsyncSession, installment_id: int, user_id: int) -> Installment | None:
    result = await session.execute(select(Installment).where(Installment.id == installment_id, Installment.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new installment plan.
async def create(session: AsyncSession, installment: Installment) -> Installment:
    session.add(installment)
    await session.flush()
    return installment


# Stage an installment for update (caller commits).
async def save(session: AsyncSession, installment: Installment) -> None:
    session.add(installment)


# Delete an installment.
async def delete(session: AsyncSession, installment: Installment) -> None:
    await session.delete(installment)


# Namespace to call repository functions (e.g. installment_repository.list_by_user).
class InstallmentRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access installment persistence.
installment_repository = InstallmentRepository()
