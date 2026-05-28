from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CycleAdvanceDecision, NotFoundError
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories import subscription_repository
from app.services.auto_expense_service import closest_subscription_cycle
from app.utils.dates import advance_by_cycle, cycle_tolerance_days


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


# Pure helper: decides whether a manual entry on `entry_date` should advance the
# subscription's `next_billing_date` cursor (Phase 3, follow-up 3b). The advance fires
# only when the entry is within tolerance of the closest cycle AND the matched cycle
# sits at-or-after the current cursor (back-dated entries before the cursor never
# rewind the schedule — that's the reverse-advance feature's job). The dataclass is
# shaped to feed both the actual write path and the preview endpoint without redoing
# the math.
def compute_subscription_advance_for_manual_entry(subscription: Subscription, entry_date: date_type) -> CycleAdvanceDecision:
    closest = closest_subscription_cycle(
        subscription.next_billing_date,
        subscription.billing_cycle,
        entry_date,
        anchor_day=subscription.anchor_day,
    )
    distance_days = abs((entry_date - closest).days)
    tolerance = cycle_tolerance_days(subscription.billing_cycle)
    in_tolerance = distance_days <= tolerance
    not_back_dated = closest >= subscription.next_billing_date
    return CycleAdvanceDecision(
        would_advance=in_tolerance and not_back_dated,
        distance_days=distance_days,
        next_expected_date=closest,
    )


# Advances `next_billing_date` past the cycle matched by a manual expense entry.
# Caller commits — this stages the change inside the expense-create transaction so the
# advance is atomic with the linked expense insert. Returns True when the cursor moved;
# False when the entry was out of tolerance or back-dated (the soft-confirm dialog
# already informed the user before they hit Save). No-op when the subscription can't
# be found or doesn't belong to the user. Per the 3b plan: at most one advance per
# save event, so we move the cursor exactly one cycle past the matched date.
async def advance_for_manual_entry(session: AsyncSession, subscription_id: int, user: User, entry_date: date_type) -> bool:
    subscription = await subscription_repository.get_by_id(session, subscription_id, user.id)
    if subscription is None:
        return False
    decision = compute_subscription_advance_for_manual_entry(subscription, entry_date)
    if not decision.would_advance:
        return False
    subscription.next_billing_date = advance_by_cycle(
        decision.next_expected_date,
        subscription.billing_cycle,
        anchor_day=subscription.anchor_day,
    )
    await subscription_repository.save(session, subscription)
    return True
