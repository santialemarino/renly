# Business logic for the read-only Payments Calendar. Aggregates upcoming
# payment events in a given month across subscriptions, installments, payment
# obligations, and credit-card due dates. No CRUD here — the underlying entities
# own their own services.

import calendar
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.credit_card import CreditCard
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.services import credit_card_service
from app.utils.dates import add_months, advance_by_cycle


# Pure value object returned from the service. Routers map this into the API response shape.
class CalendarItem:
    def __init__(
        self,
        *,
        type: str,
        date: date_type,
        name: str,
        amount: Decimal,
        currency: str,
        payment_method: str | None = None,
        credit_card_id: int | None = None,
        source_id: int,
        cuota_index: int | None = None,
        installments_count: int | None = None,
        recurrence: str | None = None,
    ) -> None:
        self.type = type
        self.date = date
        self.name = name
        self.amount = amount
        self.currency = currency
        self.payment_method = payment_method
        self.credit_card_id = credit_card_id
        self.source_id = source_id
        self.cuota_index = cuota_index
        self.installments_count = installments_count
        self.recurrence = recurrence


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
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.is_active.is_(True),
        )
    )
    subscriptions = list(result.scalars().all())

    items: list[CalendarItem] = []
    for sub in subscriptions:
        for d in _subscription_dates_in_window(sub, period_start, period_end):
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
    result = await session.execute(
        select(Installment).where(
            Installment.user_id == user.id,
            Installment.is_active.is_(True),
        )
    )
    installments = list(result.scalars().all())

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


# Payment obligations whose due_date falls in the period (active only).
async def _obligation_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    result = await session.execute(
        select(PaymentObligation).where(
            PaymentObligation.user_id == user.id,
            PaymentObligation.is_active.is_(True),
            PaymentObligation.due_date >= period_start,
            PaymentObligation.due_date <= period_end,
        )
    )
    obligations = list(result.scalars().all())
    return [
        CalendarItem(
            type="obligation",
            date=o.due_date,
            name=o.name,
            amount=o.amount,
            currency=o.currency,
            payment_method=o.payment_method,
            credit_card_id=o.credit_card_id,
            source_id=o.id,
            recurrence=o.recurrence,
        )
        for o in obligations
    ]


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
    result = await session.execute(
        select(CreditCard).where(
            CreditCard.user_id == user.id,
            CreditCard.is_active.is_(True),
        )
    )
    cards = list(result.scalars().all())
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
def _subscription_dates_in_window(
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


# Stable ordering within the same date.
_TYPE_ORDER = {
    "card_due": 0,
    "subscription": 1,
    "installment": 2,
    "obligation": 3,
}
