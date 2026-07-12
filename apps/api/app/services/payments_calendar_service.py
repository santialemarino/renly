# Business logic for the read-only Payments Calendar. Aggregates upcoming
# payment events in a given month across subscriptions, installments, payment
# obligations, and credit-card due dates. No CRUD here — the underlying entities
# own their own services.

import calendar
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CalendarItem, closest_installment_cuota, closest_subscription_cycle
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories import (
    card_reconciliation_repository,
    credit_card_repository,
    expense_repository,
    installment_repository,
    payment_obligation_repository,
    subscription_repository,
)
from app.schemas.payments_calendar import PaymentsCalendarItemResponse, PaymentsCalendarResponse
from app.services import card_reconciliation_service, credit_card_service, exchange_rate_service
from app.utils.dates import OBLIGATION_MONTH_STEP, add_months, add_months_anchored, advance_by_cycle, resolve_day_in_month, step_back_by_cycle
from app.utils.metrics import RateLookup, convert_optional


# Maps a service CalendarItem to its response shape, attaching converted_amount when requested.
# Conversion uses the rate as of the item's own event date (Phase 3, Step C). Past months on the
# calendar therefore display historical-rate amounts; future-dated items fall back to today's
# latest rate (the RateLookup's natural behaviour for dates without a stored quote).
def _to_response(
    item: CalendarItem,
    target_currency: str | None,
    lookup: RateLookup | None,
) -> PaymentsCalendarItemResponse:
    # Past-paid obligations set `conversion_date` to the linked expense's actual date
    # so the rate matches what the expenses list shows; everything else uses the cycle date.
    fx_date = item.conversion_date or item.date
    converted = convert_optional(item.amount, item.currency, target_currency, lookup, fx_date)
    return PaymentsCalendarItemResponse(
        type=item.type,
        date=item.date,
        name=item.name,
        amount=item.amount,
        currency=item.currency,
        converted_amount=converted,
        payment_method=item.payment_method,
        credit_card_id=item.credit_card_id,
        source_id=item.source_id,
        cuota_index=item.cuota_index,
        installments_count=item.installments_count,
        recurrence=item.recurrence,
        is_paid=item.is_paid,
        linked_expense_id=item.linked_expense_id,
    )


# Aggregates calendar items for the given month, converting amounts to the display currency
# when requested. Order: by date ascending, stable within the same date by type (subscription,
# installment, obligation, card_due).
async def get_calendar(
    session: AsyncSession,
    user: User,
    *,
    year: int,
    month: int,
    currency: str | None = None,
) -> PaymentsCalendarResponse:
    period_start, period_end = _month_range(year, month)

    subscription_items = await _subscription_items(session, user, period_start, period_end)
    installment_items = await _installment_items(session, user, period_start, period_end)
    obligation_items = await _obligation_items(session, user, period_start, period_end)
    card_due_items = await _card_due_items(session, user, period_start, period_end, year, month)

    items = subscription_items + installment_items + obligation_items + card_due_items
    items.sort(key=lambda i: (i.date, _TYPE_ORDER.get(i.type, 99)))
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    responses: list[PaymentsCalendarItemResponse] = []
    skipped: set[str] = set()
    for item in items:
        resp = _to_response(item, currency, lookup)
        if currency and item.currency != currency and resp.converted_amount is None:
            skipped.add(item.currency)
        responses.append(resp)
    return PaymentsCalendarResponse(
        year=year,
        month=month,
        currency=currency,
        items=responses,
        skipped_currencies=sorted(skipped),
    )


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
# inside the window that has a linked expense BOUND to it — each linked expense is matched
# to its closest cycle (same half-cycle rule as the manual-entry advance), so a cycle paid
# a few days off its date still shows its Paid badge. Each past cycle uses the LINKED
# EXPENSE's historical amount + currency so editing the subscription later doesn't rewrite
# the calendar's history. is_paid=True so the UI swaps the badge for a green Paid one.
async def _subscription_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    subscriptions = await subscription_repository.list_by_user(session, user.id, active_only=True)
    if not subscriptions:
        return []

    # Batch-load ALL linked expense rows for these subscriptions in one query — the
    # backward walker binds each expense to its closest cycle, so it needs the full
    # history, not a window slice. No N+1.
    linked_by_sub = await expense_repository.list_linked_subscription_expenses(
        session,
        user.id,
        [s.id for s in subscriptions],
    )

    items: list[CalendarItem] = []
    for sub in subscriptions:
        linked_expenses = linked_by_sub.get(sub.id, [])
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
        for cycle_date, expense in subscription_past_paid_cycles_in_window(sub, period_start, period_end, linked_expenses):
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


# Installments that fall in the period.
#
# Forward projection: emits each unpaid future installment (`current_installment..installments_count`)
# whose `start_date + (idx - 1) months` lands inside the window. Uses the installment's
# current `installment_amount` + currency (the field lock guarantees these don't drift
# after the first installment fires).
#
# Backward projection: emits each PAST installment (`1..current_installment - 1`) whose date
# lands inside the window and has a linked expense BOUND to its cuota (each linked expense
# matched to its closest cuota, same half-cycle rule as the manual-entry advance). is_paid=True.
async def _installment_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
) -> list[CalendarItem]:
    installments = await installment_repository.list_by_user(session, user.id, active_only=True)
    if not installments:
        return []

    linked_by_inst = await expense_repository.list_linked_installment_expenses(
        session,
        user.id,
        [i.id for i in installments],
    )

    items: list[CalendarItem] = []
    for inst in installments:
        linked_expenses = linked_by_inst.get(inst.id, [])
        # Forward: unpaid future installments.
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
        # Backward: past paid installments inside the window.
        for idx, cuota_date, expense in installment_past_paid_cuotas_in_window(inst, period_start, period_end, linked_expenses):
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


# Credit-card due-date events for the requested month. One event per card per bucket with
# non-zero balance, dated on the card's resolved due_day in the month. The amount is the
# bucket's running-balance snapshot at the matching statement closing date (Phase 3, Step 5 —
# running-balance model). When closing_day <= due_day, the bill due in month M is for the
# statement closed in M; otherwise it's the previous month's statement. Carryover from older
# unpaid statements is implicit in the snapshot, matching how a real bank resumen reads.
# Archived cards are included (an archived card with outstanding balance still has real due
# dates — archive is a UI filter, P04). Balances are batched: one grouped expenses + one grouped
# settlements query per DISTINCT closing date (typically 1-2 for 1-3 cards) instead of two
# queries per card×bucket.
async def _card_due_items(
    session: AsyncSession,
    user: User,
    period_start: date_type,
    period_end: date_type,
    year: int,
    month: int,
) -> list[CalendarItem]:
    cards = await credit_card_repository.list_by_user(session, user.id, active_only=False)
    if not cards:
        return []

    card_ids = [c.id for c in cards]
    card_currencies = {c.id: c.currency for c in cards}
    # We use get_card_balances purely for the list of active buckets per card —
    # the running-balance amount is recomputed at the relevant closing date below.
    buckets_by_card = await credit_card_service.get_card_balances(session, card_ids, card_currencies, user.id)

    last_day = calendar.monthrange(year, month)[1]

    # Resolve each card's due/closing date, then group cards by distinct closing date so the
    # running-balance snapshots batch into one grouped query per closing (not per card×bucket).
    due_by_card: dict[int, date_type] = {}
    closing_by_card: dict[int, date_type] = {}
    cards_by_closing: dict[date_type, list[int]] = {}
    for card in cards:
        due_day = min(card.due_day, last_day)
        due_date = date_type(year, month, due_day)
        if due_date < period_start or due_date > period_end:
            continue
        due_by_card[card.id] = due_date
        closing_date = _statement_closing_for_due(card.closing_day, due_date)
        closing_by_card[card.id] = closing_date
        cards_by_closing.setdefault(closing_date, []).append(card.id)

    snapshots: dict[tuple[int, str], Decimal] = {}
    for closing_date, ids in cards_by_closing.items():
        snapshots.update(await card_reconciliation_service.compute_bucket_balances_at(session, ids, closing_date))

    items: list[CalendarItem] = []
    for card in cards:
        due_date = due_by_card.get(card.id)
        if due_date is None:
            continue
        closing_date = closing_by_card[card.id]
        for bucket in buckets_by_card.get(card.id, []):
            snapshot = snapshots.get((card.id, bucket.currency), Decimal(0))
            if snapshot == Decimal(0):
                continue
            # Paid-marking (P04): the frozen statement amount stays, but settlements dated inside
            # (closing_date, due_date] covering it flip the badge to Paid. Negative snapshots
            # (credit balance) are not a bill — never marked paid.
            is_paid = False
            if snapshot > Decimal(0):
                settled = await card_reconciliation_repository.sum_settlements_between(session, card.id, bucket.currency, closing_date, due_date)
                is_paid = settled >= snapshot
            items.append(
                CalendarItem(
                    type="card_due",
                    date=due_date,
                    name=card.name,
                    amount=snapshot,
                    currency=bucket.currency,
                    source_id=card.id,
                    is_paid=is_paid,
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


# Returns (cycle_date, linked_expense) pairs for every PAST PAID cycle of a subscription
# inside the window. Mirrors the obligations' positional backward walk, with the pairing
# made robust for plans whose links don't all advance the cursor: each linked expense is
# BOUND to the cycle its date matches under the same closest-cycle rule the manual-entry
# advance uses (half-cycle tolerance), then the walk backward from next_billing_date emits
# every in-window cycle that owns a bound expense. Off-date payments (Mar 31 cycle paid
# Mar 29) badge their cycle; multi-jump pre-pays bind AT the cursor and stay with the
# forward (unpaid) walker until the scheduler advances past them; historical back-links
# badge their own old cycle instead of the newest one. When two expenses bind to the same
# cycle the newest wins (`linked_expenses` must be sorted DESC by expense date).
# Stops as soon as the walk passes period_start.
def subscription_past_paid_cycles_in_window(
    sub: Subscription,
    period_start: date_type,
    period_end: date_type,
    linked_expenses: list,
) -> list[tuple]:
    if not linked_expenses:
        return []

    expense_by_cycle: dict[date_type, object] = {}
    for expense in linked_expenses:
        bound = closest_subscription_cycle(
            sub.next_billing_date,
            sub.billing_cycle,
            expense.date,
            anchor_day=sub.anchor_day,
        )
        expense_by_cycle.setdefault(bound, expense)

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
            expense = expense_by_cycle.get(cursor)
            if expense is not None:
                pairs.append((cursor, expense))
        iterations += 1
    return pairs


# Returns (index, date, linked_expense) tuples for every PAST PAID cuota of an installment
# plan inside the window. Each linked expense is BOUND to the cuota index its date matches
# under the same closest-cuota rule the manual-entry advance uses, so an off-date payment
# still badges its cuota. Iteration stays bounded by [1, current_installment): indices at
# or past the cursor (multi-jump pre-pays) remain with the forward (unpaid) walker until
# the scheduler advances the counter. Newest expense wins a contested index
# (`linked_expenses` must be sorted DESC by expense date).
def installment_past_paid_cuotas_in_window(
    inst: Installment,
    period_start: date_type,
    period_end: date_type,
    linked_expenses: list,
) -> list[tuple]:
    if not linked_expenses:
        return []

    expense_by_idx: dict[int, object] = {}
    for expense in linked_expenses:
        match = closest_installment_cuota(inst.start_date, 1, inst.installments_count, expense.date)
        if match is not None:
            expense_by_idx.setdefault(match[0], expense)

    pairs: list[tuple] = []
    for idx in range(1, inst.current_installment):
        cuota_date = add_months(inst.start_date, idx - 1)
        if cuota_date < period_start or cuota_date > period_end:
            continue
        expense = expense_by_idx.get(idx)
        if expense is None:
            continue
        pairs.append((idx, cuota_date, expense))
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
