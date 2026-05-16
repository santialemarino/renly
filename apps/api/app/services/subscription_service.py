from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories import subscription_repository


# List subscriptions for a user with optional search, sorting, and archive filtering.
async def list_subscriptions(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Subscription]:
    return await subscription_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single subscription by id. Raises NotFoundError if not found.
async def get_subscription(session: AsyncSession, subscription_id: int, user: User) -> Subscription:
    subscription = await subscription_repository.get_by_id(session, subscription_id, user.id)
    if subscription is None:
        raise NotFoundError("Subscription not found.")
    return subscription


# Create a new subscription.
# anchor_day is auto-derived from next_billing_date so the scheduler can preserve
# the user's intended day-of-month across short-month clamps.
async def create_subscription(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    amount: Decimal,
    currency: str,
    billing_cycle: str,
    next_billing_date: date_type,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
) -> Subscription:
    subscription = Subscription(
        user_id=user.id,
        name=name,
        amount=amount,
        currency=currency,
        billing_cycle=billing_cycle,
        next_billing_date=next_billing_date,
        anchor_day=next_billing_date.day,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
    )
    subscription = await subscription_repository.create(session, subscription)
    await session.commit()
    return subscription


# Update an existing subscription. Only provided fields are changed.
# When next_billing_date is updated, anchor_day re-syncs to its day-of-month —
# the user is implicitly redeclaring their billing day.
async def update_subscription(
    session: AsyncSession,
    subscription_id: int,
    user: User,
    **fields: object,
) -> Subscription:
    subscription = await get_subscription(session, subscription_id, user)
    if "next_billing_date" in fields and fields["next_billing_date"] is not None:
        nbd = fields["next_billing_date"]
        if isinstance(nbd, date_type):
            fields["anchor_day"] = nbd.day
    for key, value in fields.items():
        setattr(subscription, key, value)
    await subscription_repository.save(session, subscription)
    await session.commit()
    await session.refresh(subscription)
    return subscription


# Delete a subscription.
async def delete_subscription(session: AsyncSession, subscription_id: int, user: User) -> None:
    subscription = await get_subscription(session, subscription_id, user)
    await subscription_repository.delete(session, subscription)
    await session.commit()
