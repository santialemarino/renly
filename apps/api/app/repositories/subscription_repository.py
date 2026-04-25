from sqlalchemy import asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.subscription import Subscription

_SORT_COLUMNS = {
    "name": Subscription.name,
    "amount": Subscription.amount,
    "currency": Subscription.currency,
    "billing_cycle": Subscription.billing_cycle,
    "next_billing_date": Subscription.next_billing_date,
}


# List subscriptions for a user with optional search, sorting, and active filtering.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Subscription]:
    stmt = select(Subscription).where(Subscription.user_id == user_id)
    if active_only:
        stmt = stmt.where(Subscription.is_active.is_(True))
    if search:
        stmt = stmt.where(Subscription.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else Subscription.next_billing_date
    stmt = stmt.order_by(order_clause)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single subscription by id and user_id.
async def get_by_id(session: AsyncSession, subscription_id: int, user_id: int) -> Subscription | None:
    result = await session.execute(select(Subscription).where(Subscription.id == subscription_id, Subscription.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new subscription.
async def create(session: AsyncSession, subscription: Subscription) -> Subscription:
    session.add(subscription)
    await session.flush()
    return subscription


# Stage a subscription for update (caller commits).
async def save(session: AsyncSession, subscription: Subscription) -> None:
    session.add(subscription)


# Delete a subscription.
async def delete(session: AsyncSession, subscription: Subscription) -> None:
    await session.delete(subscription)


# Namespace to call repository functions (e.g. subscription_repository.list_by_user).
class SubscriptionRepository:
    list_by_user = staticmethod(list_by_user)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access subscription persistence.
subscription_repository = SubscriptionRepository()
