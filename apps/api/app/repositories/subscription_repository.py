from datetime import date as date_type

from sqlalchemy import asc, desc, func, or_
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
) -> list[Subscription]:
    stmt = select(Subscription).where(Subscription.user_id == user_id)
    if active_only:
        if include_ids:
            stmt = stmt.where(or_(Subscription.is_active.is_(True), Subscription.id.in_(include_ids)))
        else:
            stmt = stmt.where(Subscription.is_active.is_(True))
    if search:
        stmt = stmt.where(Subscription.name.ilike(f"%{search}%"))
    sort_col = _SORT_COLUMNS.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else Subscription.next_billing_date
    stmt = stmt.order_by(order_clause)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# List every active subscription (cluster-wide) whose next_billing_date is at or before `cutoff`
# (inclusive). Powers the hourly auto-expense scan: the date bound prunes in SQL instead of loading
# every active subscription into Python each tick.
async def list_active_due(session: AsyncSession, cutoff: date_type) -> list[Subscription]:
    result = await session.execute(
        select(Subscription).where(
            Subscription.is_active.is_(True),
            Subscription.next_billing_date <= cutoff,
        )
    )
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


# Count subscriptions linked to a specific credit card.
async def count_by_credit_card(session: AsyncSession, credit_card_id: int) -> int:
    result = await session.execute(select(func.count()).where(Subscription.credit_card_id == credit_card_id))
    return int(result.scalar_one())


# Count subscriptions grouped by credit card id. Returns {card_id: count}.
async def count_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, int]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            Subscription.credit_card_id,
            func.count(),
        )
        .where(Subscription.credit_card_id.in_(credit_card_ids))
        .group_by(Subscription.credit_card_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Namespace to call repository functions (e.g. subscription_repository.list_by_user).
class SubscriptionRepository:
    list_by_user = staticmethod(list_by_user)
    list_active_due = staticmethod(list_active_due)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    count_by_credit_card = staticmethod(count_by_credit_card)
    count_by_credit_card_ids = staticmethod(count_by_credit_card_ids)


# Singleton used by services to access subscription persistence.
subscription_repository = SubscriptionRepository()
