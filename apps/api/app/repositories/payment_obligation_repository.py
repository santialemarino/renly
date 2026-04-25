from sqlalchemy import asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.payment_obligation import PaymentObligation

_SORT_COLUMNS = {
    "name": PaymentObligation.name,
    "amount": PaymentObligation.amount,
    "currency": PaymentObligation.currency,
    "due_date": PaymentObligation.due_date,
    "recurrence": PaymentObligation.recurrence,
    "category": PaymentObligation.category,
}


# List payment obligations for a user with optional search, sorting, and active filtering.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[PaymentObligation]:
    stmt = select(PaymentObligation).where(PaymentObligation.user_id == user_id)
    if active_only:
        stmt = stmt.where(PaymentObligation.is_active.is_(True))
    if search:
        stmt = stmt.where(PaymentObligation.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else PaymentObligation.due_date
    stmt = stmt.order_by(order_clause)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single payment obligation by id and user_id.
async def get_by_id(session: AsyncSession, obligation_id: int, user_id: int) -> PaymentObligation | None:
    result = await session.execute(select(PaymentObligation).where(PaymentObligation.id == obligation_id, PaymentObligation.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new payment obligation.
async def create(session: AsyncSession, obligation: PaymentObligation) -> PaymentObligation:
    session.add(obligation)
    await session.flush()
    return obligation


# Stage a payment obligation for update (caller commits).
async def save(session: AsyncSession, obligation: PaymentObligation) -> None:
    session.add(obligation)


# Delete a payment obligation.
async def delete(session: AsyncSession, obligation: PaymentObligation) -> None:
    await session.delete(obligation)


# Namespace to call repository functions (e.g. payment_obligation_repository.list_by_user).
class PaymentObligationRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access payment obligation persistence.
payment_obligation_repository = PaymentObligationRepository()
