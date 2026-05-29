from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import AdvanceResult, CycleAdvanceDecision, NotFoundError, ReverseResult
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories import subscription_repository
from app.services.auto_expense_service import closest_subscription_cycle
from app.utils.dates import advance_by_cycle, step_back_by_cycle


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
# subscription's `next_billing_date` cursor (Phase 3, follow-up 3b, revised by Item 9).
# Per Option C the advance fires ONLY when the matched cycle equals the current cursor
# (`closest == next_billing_date`). When the matched cycle is ahead (pre-pay / mis-click)
# the link is saved but the cursor stays put — the scheduler's back-fill loop + the
# partial UNIQUE INDEX dedup catch up naturally, so intermediate cycles still get
# expense rows instead of being silently skipped. `multi_jump` surfaces that case so
# Item 7's cursor-advance toast can compose the right copy.
def compute_subscription_advance_for_manual_entry(subscription: Subscription, entry_date: date_type) -> CycleAdvanceDecision:
    closest = closest_subscription_cycle(
        subscription.next_billing_date,
        subscription.billing_cycle,
        entry_date,
        anchor_day=subscription.anchor_day,
    )
    distance_days = abs((entry_date - closest).days)
    return CycleAdvanceDecision(
        would_advance=closest == subscription.next_billing_date,
        distance_days=distance_days,
        next_expected_date=closest,
        multi_jump=closest > subscription.next_billing_date,
    )


# Advances `next_billing_date` past the cycle matched by a manual expense entry.
# Caller commits — this stages the change inside the expense-create transaction so the
# advance is atomic with the linked expense insert. Returns an AdvanceResult when the
# cursor moved (Phase 3, follow-up Item 7) so the expense create response can carry
# enough context for the frontend toast; None when no advance fired (matched cycle ahead
# of or behind the cursor — multi-jump / back-dated — or the subscription can't be found
# / doesn't belong to the user). Per the 3b plan: at most one advance per save event.
async def advance_for_manual_entry(session: AsyncSession, subscription_id: int, user: User, entry_date: date_type) -> AdvanceResult | None:
    subscription = await subscription_repository.get_by_id(session, subscription_id, user.id)
    if subscription is None:
        return None
    decision = compute_subscription_advance_for_manual_entry(subscription, entry_date)
    if not decision.would_advance:
        return None
    previous = subscription.next_billing_date
    subscription.next_billing_date = advance_by_cycle(
        decision.next_expected_date,
        subscription.billing_cycle,
        anchor_day=subscription.anchor_day,
    )
    await subscription_repository.save(session, subscription)
    return AdvanceResult(
        plan_type="subscription",
        plan_id=subscription.id,
        plan_name=subscription.name,
        previous_cursor=previous.isoformat(),
        new_cursor=subscription.next_billing_date.isoformat(),
    )


# Walks `next_billing_date` back by one billing cycle (Phase 3, follow-up Item 10).
# Caller commits. Used by expense_service when the most-recent linked expense for a
# subscription is deleted or unlinked. Returns a ReverseResult with the cursor delta
# for Item 7's toast. No-op when the subscription can't be found or doesn't belong to
# the user.
async def reverse_for_unlink(session: AsyncSession, subscription_id: int, user: User) -> ReverseResult | None:
    subscription = await subscription_repository.get_by_id(session, subscription_id, user.id)
    if subscription is None:
        return None
    previous = subscription.next_billing_date
    subscription.next_billing_date = step_back_by_cycle(
        subscription.next_billing_date,
        subscription.billing_cycle,
        anchor_day=subscription.anchor_day,
    )
    await subscription_repository.save(session, subscription)
    return ReverseResult(
        plan_type="subscription",
        plan_id=subscription.id,
        plan_name=subscription.name,
        previous_cursor=previous.isoformat(),
        new_cursor=subscription.next_billing_date.isoformat(),
    )
