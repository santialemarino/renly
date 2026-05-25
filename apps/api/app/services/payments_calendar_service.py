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
from app.utils.dates import add_months, add_months_anchored, advance_by_cycle, resolve_day_in_month, step_back_by_cycle


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


# Subscription charges that fall in the period.
#
# Forward projection: walks from `next_billing_date` forward, honouring billing_cycle +
# anchor_day, and emits every UNPAID future cycle inside the window. Uses the subscription's
# CURRENT amount + currency.
#
# Backward projection: walks from `next_billing_date` backward and emits every PAST cycle
# inside the window whose scheduler-emitted expense row exists (matched via the partial
# UNIQUE INDEX on `(subscription_id, date)`). Each past cycle uses the LINKED EXPENSE's
# historical amount + currency so editing the subscription later doesn't rewrite the
# calendar's history. is_paid=True so the UI swaps the badge for a green Paid one.
async def _subscription_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    subscriptions = await subscription_repository.list_by_user(session, user.id, active_only=True)
    if not subscriptions:
        return []

    # Batch-load auto-emitted expense rows for these subscriptions across the window in
    # one query — backward walker reads from the resulting dict, no N+1.
    paid_by_sub = await expense_repository.linked_subscription_expenses_by_date(
        session,
        user.id,
        [s.id for s in subscriptions],
        period_start,
        period_end,
    )

    items: list[CalendarItem] = []
    for sub in subscriptions:
        paid_expenses = paid_by_sub.get(sub.id, {})
        # Forward: unpaid future cycles.
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
                    is_paid=False,
                )
            )
        # Backward: past paid cycles inside the window.
        for cycle_date, expense in subscription_past_paid_cycles_in_window(sub, period_start, period_end, paid_expenses):
            items.append(
                CalendarItem(
                    type="subscription",
                    date=cycle_date,
                    name=sub.name,
                    amount=expense.amount,
                    currency=expense.currency,
                    payment_method=sub.payment_method,
                    credit_card_id=sub.credit_card_id,
                    source_id=sub.id,
                    is_paid=True,
                    conversion_date=expense.date,
                    linked_expense_id=expense.id,
                )
            )
    return items


# Installment cuotas that fall in the period.
#
# Forward projection: emits each unpaid future cuota (`current_installment..installments_count`)
# whose `start_date + (idx - 1) months` lands inside the window. Uses the installment's
# current `installment_amount` + currency (the field lock guarantees these don't drift
# after the first cuota fires).
#
# Backward projection: emits each PAST cuota (`1..current_installment - 1`) whose date
# lands inside the window AND whose scheduler-emitted expense row exists. is_paid=True.
async def _installment_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    installments = await installment_repository.list_by_user(session, user.id, active_only=True)
    if not installments:
        return []

    paid_by_inst = await expense_repository.linked_installment_expenses_by_date(
        session,
        user.id,
        [i.id for i in installments],
        period_start,
        period_end,
    )

    items: list[CalendarItem] = []
    for inst in installments:
        paid_expenses = paid_by_inst.get(inst.id, {})
        # Forward: unpaid future cuotas.
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
                    is_paid=False,
                )
            )
        # Backward: past paid cuotas inside the window.
        for idx in range(1, inst.current_installment):
            cuota_date = add_months(inst.start_date, idx - 1)
            if cuota_date < period_start:
                continue
            if cuota_date > period_end:
                continue
            expense = paid_expenses.get(cuota_date)
            if expense is None:
                continue
            items.append(
                CalendarItem(
                    type="installment",
                    date=cuota_date,
                    name=inst.name,
                    amount=expense.amount,
                    currency=expense.currency,
                    payment_method=inst.payment_method,
                    credit_card_id=inst.credit_card_id,
                    source_id=inst.id,
                    cuota_index=idx,
                    installments_count=inst.installments_count,
                    is_paid=True,
                    conversion_date=expense.date,
                    linked_expense_id=expense.id,
                )
            )
    return items


# Payment obligation occurrences that fall in the period.
#
# Forward projection: walks the recurrence forward from `next_due_date` and emits every
# upcoming UNPAID occurrence inside the window — matches the subscription pattern so a
# monthly ABL surfaces every month. One-off obligations emit at most one forward event
# (only when `next_due_date` lies inside the window). Forward events use the obligation's
# CURRENT amount + currency ("what next will cost").
#
# Backward projection (Phase 3, Step E — recurring only): walks backward from
# `next_due_date` one cycle per linked expense and emits every past occurrence inside
# the window. Each emitted cycle carries the LINKED EXPENSE'S amount + currency (the
# actual historical paid values), so editing the obligation later doesn't retroactively
# rewrite past Paid badges on the calendar. Pairing: backward step `i` (newest-first)
# uses linked-expense `i` (newest-first by expense date). One-off obligations don't
# backward-walk because paying a one-off archives it (it disappears from the list).
async def _obligation_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    # Fetch every active obligation in one query, then split per-direction in Python.
    # Forward projection still needs the original anchor-before-window filter; the
    # backward walk uses anchors AFTER the window too.
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

    # Batch-load linked expenses per obligation in one query (no N+1). Sorted DESC by
    # date so backward step `i` pairs naturally with `linked_by_obligation[id][i]`.
    linked_by_obligation: dict[int, list] = {}
    if backward_ids:
        linked_by_obligation = await expense_repository.list_linked_obligation_expenses(session, user.id, backward_ids)

    items: list[CalendarItem] = []
    # Forward (unpaid future) — uses obligation's CURRENT amount + currency.
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
    # Backward (past paid) — uses the LINKED EXPENSE's historical amount + currency.
    for o in backward_obligations:
        linked = linked_by_obligation.get(o.id, [])
        if not linked:
            continue
        for occurrence, expense in obligation_past_paid_cycles_in_window(o, period_start, period_end, linked):
            items.append(
                CalendarItem(
                    type="obligation",
                    date=occurrence,
                    name=o.name,
                    amount=expense.amount,
                    currency=expense.currency,
                    payment_method=o.payment_method,
                    credit_card_id=o.credit_card_id,
                    source_id=o.id,
                    recurrence=o.recurrence,
                    is_paid=True,
                    # FX conversion anchors on the actual paid date (not the cycle date),
                    # so the calendar's converted amount matches what the linked expense
                    # shows on the standalone Expenses list.
                    conversion_date=expense.date,
                    linked_expense_id=expense.id,
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


# Returns (cycle_date, linked_expense) pairs for every PAST cycle of a subscription
# inside the window whose scheduler-emitted expense row exists. Walks backward from
# next_billing_date one cycle at a time, matching each cursor against the supplied
# dict of paid expenses by date (the partial UNIQUE INDEX on (subscription_id, date)
# guarantees at most one expense per cycle, so the dict lookup is unambiguous).
# Stops as soon as the cursor walks past period_start (further past cycles can't
# intersect the window).
def subscription_past_paid_cycles_in_window(
    sub: Subscription,
    period_start: date_type,
    period_end: date_type,
    paid_expenses_by_date: dict[date_type, object],
) -> list[tuple]:
    if not paid_expenses_by_date:
        return []

    pairs: list[tuple] = []
    cursor = sub.next_billing_date
    iterations = 0
    while iterations < 1000:
        prev = step_back_by_cycle(cursor, sub.billing_cycle, anchor_day=sub.anchor_day)
        if prev >= cursor:
            break
        cursor = prev
        if cursor < period_start:
            break
        if cursor <= period_end:
            expense = paid_expenses_by_date.get(cursor)
            if expense is not None:
                pairs.append((cursor, expense))
        iterations += 1
    return pairs


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

    # Use obligation.anchor_day (NOT anchor.day) so day-31 obligations don't drift
    # after a short-month clamp earlier in the recurrence.
    anchor_day = obligation.anchor_day
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


# Returns (cycle_date, linked_expense) pairs for every PAST PAID occurrence of a
# recurring payment obligation that lands inside the window (Phase 3, Step E).
# Walks backward from next_due_date one cycle per linked expense — because each
# linked expense advances next_due_date exactly one cycle, the first N backward
# steps correspond to the N linked expenses regardless of when those payments
# were actually dated.
# `linked_expenses` must be sorted DESC by expense date so that backward step `i`
# pairs with `linked_expenses[i]` (newest cycle ↔ newest expense). Cycles outside
# the window are skipped; cycles before period_start short-circuit the walk.
# One-off obligations don't backward-walk because paying a one-off archives it.
def obligation_past_paid_cycles_in_window(
    obligation: PaymentObligation,
    period_start: date_type,
    period_end: date_type,
    linked_expenses: list,
) -> list[tuple]:
    months_step = OBLIGATION_MONTH_STEP.get(obligation.recurrence or "")
    if months_step is None or not linked_expenses:
        return []

    # Use the obligation's stored anchor_day, NOT next_due_date.day, so day-31 anchors
    # don't drift after a short-month clamp (same fix as subscriptions' anchor_day).
    anchor_day = obligation.anchor_day
    cursor = obligation.next_due_date
    pairs: list[tuple] = []
    step = 0
    while step < len(linked_expenses) and step < 1000:
        prev = add_months_anchored(cursor, -months_step, anchor_day)
        if prev >= cursor:
            break
        cursor = prev
        if cursor < period_start:
            break
        if cursor <= period_end:
            pairs.append((cursor, linked_expenses[step]))
        step += 1
    return pairs


# Stable ordering within the same date.
_TYPE_ORDER = {
    "card_due": 0,
    "subscription": 1,
    "installment": 2,
    "obligation": 3,
}
