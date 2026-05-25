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
    expense_repository,
    installment_repository,
    payment_obligation_repository,
    subscription_repository,
)
from app.services import card_reconciliation_service, credit_card_service
from app.services.payment_obligation_service import OBLIGATION_MONTH_STEP
from app.utils.dates import add_months, add_months_anchored, advance_by_cycle, resolve_day_in_month


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


# Payment obligation occurrences that fall in the period.
#
# Forward projection: walks the recurrence forward from `next_due_date` and emits every
# upcoming UNPAID occurrence inside the window — matches the subscription pattern so a
# monthly ABL surfaces every month. One-off obligations emit at most one forward event
# (only when `next_due_date` lies inside the window).
#
# Backward projection (Phase 3, Step E — recurring only): walks backward from
# `next_due_date` and emits every PAST occurrence inside the window whose cycle period
# `(prev_anchor, occurrence]` contains a linked expense (i.e. expense.payment_obligation_id
# matches AND expense.date falls inside that period). Those are marked `is_paid=True` so
# the UI swaps the default obligation badge for a green "Paid" badge. One-off obligations
# don't backward-walk because paying a one-off archives it (it disappears from the list).
async def _obligation_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    # Fetch every active obligation — forward projection still needs the original anchor-
    # before-window filter, but the backward walk uses anchors AFTER the window too.
    # We load every active obligation in one query and split per-direction in Python.
    obligations = await payment_obligation_repository.list_by_user(session, user.id, active_only=True)
    if not obligations:
        return []

    # Forward-projection candidates: anchor must be at or before period_end (anchors past
    # the window can't reach back when walking forward).
    forward_obligations = [o for o in obligations if o.next_due_date <= period_end]

    # Backward-projection candidates: only recurring obligations (one-offs would be archived
    # on payment) AND the anchor must be after period_start (otherwise there's no prior cycle
    # to walk into the window).
    backward_obligations = [o for o in obligations if o.recurrence is not None and o.next_due_date > period_start]
    backward_ids = [o.id for o in backward_obligations]

    # Batch-load linked-expense COUNTS per obligation in one query (no N+1).
    # Counts (not dates) — each linked expense corresponds to one cycle of advance,
    # so the count sizes the backward walk regardless of when the payments were dated.
    paid_count_by_obligation: dict[int, int] = {}
    if backward_ids:
        paid_count_by_obligation = await expense_repository.count_linked_obligations(session, user.id, backward_ids)

    items: list[CalendarItem] = []
    # Forward (unpaid future).
    for o in forward_obligations:
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
                    is_paid=False,
                )
            )
    # Backward (past paid).
    for o in backward_obligations:
        linked_count = paid_count_by_obligation.get(o.id, 0)
        if linked_count <= 0:
            continue
        for occurrence in obligation_past_paid_dates_in_window(o, period_start, period_end, linked_count):
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
                    is_paid=True,
                )
            )
    return items


# Credit-card due-date events for the requested month. One event per active card per
# bucket with non-zero balance, dated on the card's resolved due_day in the month.
# The amount is the bucket's running-balance snapshot at the matching statement closing
# date (Phase 3, Step 5 — running-balance model). When closing_day <= due_day, the
# bill due in month M is for the statement closed in M; otherwise it's the previous
# month's statement. Carryover from older unpaid statements is implicit in the snapshot,
# matching how a real bank resumen reads.
# Issues one balance lookup per (card, currency) — small N in practice (1–3 cards per user).
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
    # We use get_card_balances purely for the list of active buckets per card —
    # the running-balance amount is recomputed at the relevant closing date below.
    buckets_by_card = await credit_card_service.get_card_balances(session, card_ids, card_currencies)

    last_day = calendar.monthrange(year, month)[1]
    items: list[CalendarItem] = []
    for card in cards:
        due_day = min(card.due_day, last_day)
        due_date = date_type(year, month, due_day)
        if due_date < period_start or due_date > period_end:
            continue
        closing_date = _statement_closing_for_due(card.closing_day, due_date)
        for bucket in buckets_by_card.get(card.id, []):
            snapshot = await card_reconciliation_service.compute_bucket_balance_at(session, card.id, bucket.currency, closing_date)
            if snapshot == Decimal(0):
                continue
            items.append(
                CalendarItem(
                    type="card_due",
                    date=due_date,
                    name=card.name,
                    amount=snapshot,
                    currency=bucket.currency,
                    source_id=card.id,
                )
            )
    return items


# Resolves the statement closing date that a given due_date is paying for.
# When closing_day <= due_day (closing happens before due in the same month), the bill
# due in month M is for M's statement. Otherwise it's the previous month's statement
# (closing in M is in the future relative to due in M, so the bill is for the prior cycle).
def _statement_closing_for_due(closing_day: int, due_date: date_type) -> date_type:
    candidate_in_month = resolve_day_in_month(closing_day, due_date.year, due_date.month)
    if candidate_in_month <= due_date:
        return candidate_in_month
    prev_total = due_date.year * 12 + (due_date.month - 1) - 1
    prev_year, prev_month = divmod(prev_total, 12)
    prev_month += 1
    return resolve_day_in_month(closing_day, prev_year, prev_month)


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


# Returns every UNPAID forward occurrence of a payment obligation inside the window.
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
    months_step = OBLIGATION_MONTH_STEP.get(obligation.recurrence or "")
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


# Returns every PAST PAID occurrence of a recurring payment obligation inside the window
# (Phase 3, Step E). Walks backward from next_due_date one cycle per linked expense
# (count-based, NOT date-matched per cycle) — because each linked expense advances
# next_due_date exactly one cycle, the first N backward steps correspond to the N
# linked expenses regardless of when those payments were actually dated. Stops early
# when the cursor walks past period_start (further past cycles can't reach the window).
# One-off obligations don't backward-walk because paying a one-off archives it — it
# disappears from the active list entirely.
def obligation_past_paid_dates_in_window(
    obligation: PaymentObligation,
    period_start: date_type,
    period_end: date_type,
    linked_expense_count: int,
) -> list[date_type]:
    months_step = OBLIGATION_MONTH_STEP.get(obligation.recurrence or "")
    if months_step is None or linked_expense_count <= 0:
        return []

    anchor_day = obligation.next_due_date.day
    cursor = obligation.next_due_date
    dates: list[date_type] = []
    steps = 0
    while steps < linked_expense_count and steps < 1000:
        prev = add_months_anchored(cursor, -months_step, anchor_day)
        if prev >= cursor:
            break
        cursor = prev
        if cursor < period_start:
            break
        if cursor <= period_end:
            dates.append(cursor)
        steps += 1
    return dates


# Stable ordering within the same date.
_TYPE_ORDER = {
    "card_due": 0,
    "subscription": 1,
    "installment": 2,
    "obligation": 3,
}
