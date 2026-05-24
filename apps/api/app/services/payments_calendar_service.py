# Business logic for the read-only Payments Calendar. Aggregates upcoming
# payment events in a given month across subscriptions, installments, payment
# obligations, and credit-card due dates. No CRUD here — the underlying entities
# own their own services.

import calendar
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CalendarItem
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories import (
    credit_card_repository,
    installment_repository,
    payment_obligation_repository,
    subscription_repository,
)
from app.services import credit_card_service
from app.utils.dates import add_months, add_months_anchored, advance_by_cycle


# Aggregates calendar items for the given month. Order: by date ascending,
# stable within the same date by type (subscription, installment, obligation, card_due).
async def get_calendar(session: AsyncSession, user: User, *, year: int, month: int) -> list[CalendarItem]:
    period_start, period_end = _month_range(year, month)

    subscription_items = await _subscription_items(session, user, period_start, period_end)
    installment_items = await _installment_items(session, user, period_start, period_end)
    obligation_items = await _obligation_items(session, user, period_start, period_end)
    card_due_items = await _card_due_items(session, user, period_start, period_end, year, month)

    items = subscription_items + installment_items + obligation_items + card_due_items
    items.sort(key=lambda i: (i.date, _TYPE_ORDER.get(i.type, 99)))
    return items


# --- Aggregators per source ---


# Returns the inclusive first and last day of the requested calendar month.
def _month_range(year: int, month: int) -> tuple[date_type, date_type]:
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, 1), date_type(year, month, last_day)


# Subscription charges that fall in the period. Walks from the saved next_billing_date
# forward, honouring billing_cycle + anchor_day, and emits every cycle date inside the window.
async def _subscription_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    subscriptions = await subscription_repository.list_by_user(session, user.id, active_only=True)

    items: list[CalendarItem] = []
    for sub in subscriptions:
        for d in subscription_dates_in_window(sub, period_start, period_end):
            items.append(
                CalendarItem(
                    type="subscription",
                    date=d,
                    name=sub.name,
                    amount=sub.amount,
                    currency=sub.currency,
                    payment_method=sub.payment_method,
                    credit_card_id=sub.credit_card_id,
                    source_id=sub.id,
                )
            )
    return items


# Installment cuotas that fall in the period. Each cuota date is start_date + (idx - 1) months,
# clamped to the last day of the target month.
async def _installment_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    installments = await installment_repository.list_by_user(session, user.id, active_only=True)

    items: list[CalendarItem] = []
    for inst in installments:
        for idx in range(inst.current_installment, inst.installments_count + 1):
            cuota_date = add_months(inst.start_date, idx - 1)
            if cuota_date < period_start:
                continue
            if cuota_date > period_end:
                break
            items.append(
                CalendarItem(
                    type="installment",
                    date=cuota_date,
                    name=inst.name,
                    amount=inst.installment_amount,
                    currency=inst.currency,
                    payment_method=inst.payment_method,
                    credit_card_id=inst.credit_card_id,
                    source_id=inst.id,
                    cuota_index=idx,
                    installments_count=inst.installments_count,
                )
            )
    return items


# Payment obligation occurrences that fall in the period. For one-off obligations
# this is at most one event (only when `next_due_date` lies inside the window).
# For recurring obligations we walk the recurrence forward from `next_due_date`
# (anchor-aware via add_months_anchored) and emit every occurrence inside the
# window — matches the subscription pattern so a monthly ABL surfaces every month.
async def _obligation_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    # Fetch only obligations whose anchor is at or before the window's end —
    # anything anchored further in the future can't project into this window
    # (we don't walk backwards).
    obligations = await payment_obligation_repository.list_active_anchored_to_or_before(session, user.id, period_end)

    items: list[CalendarItem] = []
    for o in obligations:
        for occurrence in obligation_dates_in_window(o, period_start, period_end):
            items.append(
                CalendarItem(
                    type="obligation",
                    date=occurrence,
                    name=o.name,
                    amount=o.amount,
                    currency=o.currency,
                    payment_method=o.payment_method,
                    credit_card_id=o.credit_card_id,
                    source_id=o.id,
                    recurrence=o.recurrence,
                )
            )
    return items


# Credit-card due-date events for the requested month. One event per active card per
# bucket with non-zero balance. The card's due_day is clamped to the last day of the
# target month (handles closing_day=31 in Feb, etc.).
# Note: bucket amount is today's outstanding — Step 5 will tie this to statement periods.
async def _card_due_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
    year: int,
    month: int,
) -> list[CalendarItem]:
    cards = await credit_card_repository.list_by_user(session, user.id, active_only=True)
    if not cards:
        return []

    card_ids = [c.id for c in cards]
    card_currencies = {c.id: c.currency for c in cards}
    balances = await credit_card_service.get_card_balances(session, card_ids, card_currencies)

    last_day = calendar.monthrange(year, month)[1]
    items: list[CalendarItem] = []
    for card in cards:
        due_day = min(card.due_day, last_day)
        due_date = date_type(year, month, due_day)
        if due_date < period_start or due_date > period_end:
            continue
        for bucket in balances.get(card.id, []):
            if bucket.balance == Decimal(0):
                continue
            items.append(
                CalendarItem(
                    type="card_due",
                    date=due_date,
                    name=card.name,
                    amount=bucket.balance,
                    currency=bucket.currency,
                    source_id=card.id,
                )
            )
    return items


# Yields every cycle date for a subscription that lands inside [period_start, period_end].
# Starts from the saved next_billing_date, walks the cycle (anchor-aware for monthly /
# quarterly / annual), and skips dates before the window.
def subscription_dates_in_window(
    sub: Subscription,
    period_start: date_type,
    period_end: date_type,
) -> list[date_type]:
    cursor = sub.next_billing_date
    dates: list[date_type] = []
    iterations = 0
    while cursor <= period_end and iterations < 1000:
        if cursor >= period_start:
            dates.append(cursor)
        nxt = advance_by_cycle(cursor, sub.billing_cycle, anchor_day=sub.anchor_day)
        if nxt <= cursor:
            break
        cursor = nxt
        iterations += 1
    return dates


# Returns every occurrence of a payment obligation that lands inside the window.
# One-off obligations (recurrence=None) yield at most one date: the stored anchor
# when it's inside the window. Recurring obligations walk forward from the anchor
# using add_months_anchored — month-step is derived from recurrence (monthly=1,
# bimonthly=2, quarterly=3, annual=12). The anchor day-of-month is preserved
# across short-month clamps just like subscriptions and installments.
def obligation_dates_in_window(
    obligation: PaymentObligation,
    period_start: date_type,
    period_end: date_type,
) -> list[date_type]:
    anchor = obligation.next_due_date
    months_step = _OBLIGATION_MONTH_STEP.get(obligation.recurrence or "")
    if months_step is None:
        # One-off — emit only if the anchor itself is in the window.
        return [anchor] if period_start <= anchor <= period_end else []

    anchor_day = anchor.day
    dates: list[date_type] = []
    cursor = anchor
    iterations = 0
    # Safety cap mirrors the subscription helper so a corrupt record can't loop forever.
    while cursor <= period_end and iterations < 1000:
        if cursor >= period_start:
            dates.append(cursor)
        nxt = add_months_anchored(cursor, months_step, anchor_day)
        if nxt <= cursor:
            break
        cursor = nxt
        iterations += 1
    return dates


# Recurrence pattern → calendar-month step used when projecting forward.
_OBLIGATION_MONTH_STEP = {
    "monthly": 1,
    "bimonthly": 2,
    "quarterly": 3,
    "annual": 12,
}


# Stable ordering within the same date.
_TYPE_ORDER = {
    "card_due": 0,
    "subscription": 1,
    "installment": 2,
    "obligation": 3,
}
