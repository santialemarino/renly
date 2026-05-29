from sqlalchemy import Date, asc, cast, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.installment import Installment

# Derived expression matching the `InstallmentResponse.next_cuota_date` computed field.
# Lets the table sort by next-installment order without an O(n) post-query Python re-sort —
# `make_interval` is a PostgreSQL built-in that handles month-end clamping the same
# way `add_months` does on the Python side (e.g. Jan 31 + 1 month → Feb 28), so the
# SQL order matches the response values exactly. Cast back to Date because
# `date + interval` returns timestamp in PG.
_next_cuota_date_expr = cast(
    Installment.start_date + func.make_interval(0, Installment.current_installment - 1),
    Date,
)

_SORT_COLUMNS = {
    "name": Installment.name,
    "total_amount": Installment.total_amount,
    "installment_amount": Installment.installment_amount,
    "currency": Installment.currency,
    "installments_count": Installment.installments_count,
    "current_installment": Installment.current_installment,
    "start_date": Installment.start_date,
    "next_cuota_date": _next_cuota_date_expr,
}


# List installments for a user with optional search, sorting, and active filtering.
# `include_ids` (only honoured when `active_only=True`) widens the active filter so
# the listed archived plans pointed to by include_ids are still returned — used by
# the expense form's edit dialog so a row linked to a since-archived plan can still
# render the plan name in the linked-FK dropdown (Phase 3 audit-round-3 follow-up).
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
    include_ids: list[int] | None = None,
) -> list[Installment]:
    stmt = select(Installment).where(Installment.user_id == user_id)
    if active_only:
        if include_ids:
            stmt = stmt.where(or_(Installment.is_active.is_(True), Installment.id.in_(include_ids)))
        else:
            stmt = stmt.where(Installment.is_active.is_(True))
    if search:
        stmt = stmt.where(Installment.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    # Default order: most-recent first by the derived next-installment date — keeps the
    # default view aligned with what the table now leads with.
    order_clause = order_fn(sort_col) if sort_col is not None else _next_cuota_date_expr.desc()
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
