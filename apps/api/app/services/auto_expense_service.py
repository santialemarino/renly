# Business logic for retroactive auto-generation of expense_entries from active
# subscriptions and installment plans. The hourly scheduler job calls
# generate_auto_expenses(); each tick processes ONLY users whose local-time-now
# hour equals AUTO_EXPENSES_HOUR_LOCAL (= 1), so each user's charges fire at
# their own local 01:00. Per-user "today" is computed in the user's IANA tz.
# Idempotent across re-runs (dedup-keyed on (source plan, date)).

import logging
from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.expense_entry import ExpenseEntry
from app.models.installment import Installment
from app.models.subscription import Subscription
from app.repositories import user_settings_repository
from app.utils.dates import (
    add_months,
    advance_by_cycle,
    local_hour_for_user,
    step_back_by_cycle,
    today_in_timezone,
)

logger = logging.getLogger(__name__)

SOURCE_SUBSCRIPTION = "subscription"
SOURCE_INSTALLMENT = "installment"

# Hour-of-day (in each user's local timezone) at which the scheduler emits their
# pending auto-expenses. The hourly cron checks this against every user's
# local-time-now and processes only the matching users that tick.
AUTO_EXPENSES_HOUR_LOCAL = 1


# Returns the list of cycle dates a subscription should have emitted up to and
# including today, given its current next_billing_date and billing cycle.
# `anchor_day` defaults to next_billing_date.day so callers without an explicit
# anchor still get sensible behaviour; the scheduler always passes the stored
# subscription.anchor_day to keep the user's intended day across short-month clamps.
# Pure function — does not advance the subscription record itself.
def subscription_dates_to_emit(
    next_billing_date: date_type,
    billing_cycle: str,
    today: date_type,
    *,
    anchor_day: int | None = None,
) -> list[date_type]:
    if anchor_day is None:
        anchor_day = next_billing_date.day
    dates: list[date_type] = []
    cursor = next_billing_date
    # Safety cap to avoid runaway loops on bad data (e.g. unknown cycle landing on the same day).
    while cursor <= today and len(dates) < 1000:
        dates.append(cursor)
        nxt = advance_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
        if nxt <= cursor:
            break
        cursor = nxt
    return dates


# Returns the subscription cycle date closest to `target_date` measured by absolute
# day distance (Phase 3, follow-up 3b). Walks the cycle anchored on next_billing_date
# forward or backward — including PAST cycles before the current cursor — and picks
# the candidate with the smallest |target - cycle|. Pure function; the caller checks
# whether the matched cycle equals the current cursor before advancing (Item 9, Option C).
# The closest-cycle math implicitly enforces a half-cycle window around the cursor — an
# entry within half a cycle of the cursor matches it; further out, it matches a neighbour
# and the strict-equality predicate refuses to advance. Defensive safety cap on the walk
# prevents runaway loops on degenerate cycles.
def closest_subscription_cycle(
    next_billing_date: date_type,
    billing_cycle: str,
    target_date: date_type,
    *,
    anchor_day: int | None = None,
) -> date_type:
    if anchor_day is None:
        anchor_day = next_billing_date.day
    # Forward walk first if the target is at-or-after the cursor.
    if target_date >= next_billing_date:
        cursor = next_billing_date
        steps = 0
        while steps < 1000:
            nxt = advance_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
            if nxt <= cursor or nxt > target_date:
                break
            cursor = nxt
            steps += 1
        nxt = advance_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
        if nxt <= cursor:
            return cursor
        return cursor if abs((cursor - target_date).days) <= abs((nxt - target_date).days) else nxt
    # Backward walk: the target is before the current cursor.
    cursor = next_billing_date
    steps = 0
    while steps < 1000:
        prev = step_back_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
        if prev >= cursor or prev < target_date:
            break
        cursor = prev
        steps += 1
    prev = step_back_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
    if prev >= cursor:
        return cursor
    return cursor if abs((cursor - target_date).days) <= abs((prev - target_date).days) else prev


# Returns the (index, date) of the installment closest to `target_date` for an installment
# plan, or None when the plan is already fully paid (`current_installment > installments_count`).
# Indices are 1-based; date = add_months(start_date, idx - 1). Pure function; the caller
# checks whether the matched installment equals the current cursor before advancing
# (Item 9, Option C). The closest-installment math implicitly enforces a half-month
# window around the cursor.
def closest_installment_cuota(
    start_date: date_type,
    current_installment: int,
    installments_count: int,
    target_date: date_type,
) -> tuple[int, date_type] | None:
    if current_installment > installments_count:
        return None
    # Closed-form approximation: compare target's month offset from start_date to the
    # installment grid, then check the 1-step neighbourhood to absorb the short-month clamp.
    months_diff = (target_date.year - start_date.year) * 12 + (target_date.month - start_date.month)
    approx_idx = months_diff + 1
    candidates: list[tuple[int, date_type]] = []
    for idx in (approx_idx - 1, approx_idx, approx_idx + 1):
        clamped = max(1, min(idx, installments_count))
        cuota_date = add_months(start_date, clamped - 1)
        candidates.append((clamped, cuota_date))
    best = min(candidates, key=lambda pair: abs((pair[1] - target_date).days))
    return best


# Returns (index, date) pairs an installment plan should have emitted up to and
# including today. Pure function — does not mutate the installment record.
# Indices are 1-based; date is start_date + (index - 1) months.
def installment_cuotas_to_emit(
    start_date: date_type,
    current_installment: int,
    installments_count: int,
    today: date_type,
) -> list[tuple[int, date_type]]:
    cuotas: list[tuple[int, date_type]] = []
    idx = current_installment
    while idx <= installments_count:
        cuota_date = add_months(start_date, idx - 1)
        if cuota_date > today:
            break
        cuotas.append((idx, cuota_date))
        idx += 1
    return cuotas


# Auto-generates expense entries for active subscriptions and installments
# belonging to users whose local-time-now hour equals AUTO_EXPENSES_HOUR_LOCAL.
# Users with no stored timezone fall back to UTC. Idempotent on re-runs.
# Returns the count of expense_entries created.
async def generate_auto_expenses(session: AsyncSession, *, now_utc: datetime | None = None) -> int:
    now_utc = now_utc or datetime.now(UTC)

    user_timezones = await user_settings_repository.get_all_timezones(session)

    sub_count = await _generate_subscription_expenses(session, now_utc, user_timezones)
    inst_count = await _generate_installment_expenses(session, now_utc, user_timezones)

    if sub_count or inst_count:
        await session.commit()
    return sub_count + inst_count


# Emits expense_entries for active subscriptions belonging to eligible users
# (those whose local hour matches AUTO_EXPENSES_HOUR_LOCAL on this tick).
async def _generate_subscription_expenses(
    session: AsyncSession,
    now_utc: datetime,
    user_timezones: dict[int, str],
) -> int:
    result = await session.execute(select(Subscription).where(Subscription.is_active.is_(True)))
    subscriptions = list(result.scalars().all())
    if not subscriptions:
        return 0

    # Filter to subscriptions whose user is currently at AUTO_EXPENSES_HOUR_LOCAL
    # AND whose next_billing_date has been reached in that user's local tz.
    pending: list[tuple[Subscription, date_type]] = []
    for sub in subscriptions:
        user_tz = user_timezones.get(sub.user_id)
        if local_hour_for_user(now_utc, user_tz) != AUTO_EXPENSES_HOUR_LOCAL:
            continue
        today_for_user = today_in_timezone(now_utc, user_tz)
        if sub.next_billing_date > today_for_user:
            continue
        pending.append((sub, today_for_user))
    if not pending:
        return 0

    sub_ids = [s.id for s, _ in pending]
    existing = await _existing_subscription_dates(session, sub_ids)

    created = 0
    for sub, today_for_user in pending:
        dates = subscription_dates_to_emit(
            sub.next_billing_date,
            sub.billing_cycle,
            today_for_user,
            anchor_day=sub.anchor_day,
        )
        if not dates:
            continue
        for d in dates:
            if (sub.id, d) in existing:
                continue
            session.add(
                ExpenseEntry(
                    user_id=sub.user_id,
                    date=d,
                    amount=sub.amount,
                    currency=sub.currency,
                    notes=sub.name,
                    payment_method=sub.payment_method,
                    credit_card_id=sub.credit_card_id,
                    source=SOURCE_SUBSCRIPTION,
                    subscription_id=sub.id,
                )
            )
            created += 1
        # Advance to the first cycle strictly after today.
        next_after = advance_by_cycle(dates[-1], sub.billing_cycle, anchor_day=sub.anchor_day)
        sub.next_billing_date = next_after
        session.add(sub)

    if created:
        await session.flush()
        logger.info("Auto-expenses: created %d subscription charges at %s UTC.", created, now_utc.isoformat())
    return created


# Emits expense_entries for active installment plans belonging to eligible users.
async def _generate_installment_expenses(
    session: AsyncSession,
    now_utc: datetime,
    user_timezones: dict[int, str],
) -> int:
    result = await session.execute(select(Installment).where(Installment.is_active.is_(True)))
    installments = list(result.scalars().all())
    if not installments:
        return 0

    pending: list[tuple[Installment, date_type]] = []
    for inst in installments:
        user_tz = user_timezones.get(inst.user_id)
        if local_hour_for_user(now_utc, user_tz) != AUTO_EXPENSES_HOUR_LOCAL:
            continue
        if inst.current_installment > inst.installments_count:
            continue
        today_for_user = today_in_timezone(now_utc, user_tz)
        if add_months(inst.start_date, inst.current_installment - 1) > today_for_user:
            continue
        pending.append((inst, today_for_user))
    if not pending:
        return 0

    inst_ids = [i.id for i, _ in pending]
    existing = await _existing_installment_dates(session, inst_ids)

    created = 0
    for inst, today_for_user in pending:
        cuotas = installment_cuotas_to_emit(
            inst.start_date,
            inst.current_installment,
            inst.installments_count,
            today_for_user,
        )
        if not cuotas:
            continue
        for _idx, cuota_date in cuotas:
            if (inst.id, cuota_date) in existing:
                continue
            session.add(
                ExpenseEntry(
                    user_id=inst.user_id,
                    date=cuota_date,
                    amount=inst.installment_amount,
                    currency=inst.currency,
                    notes=inst.name,
                    payment_method=inst.payment_method,
                    credit_card_id=inst.credit_card_id,
                    source=SOURCE_INSTALLMENT,
                    installment_id=inst.id,
                )
            )
            created += 1
        # Advance the installment counter past the last emitted index; flip the plan
        # inactive once we're past the final installment.
        last_idx = cuotas[-1][0]
        inst.current_installment = last_idx + 1
        if inst.current_installment > inst.installments_count:
            inst.is_active = False
        session.add(inst)

    if created:
        await session.flush()
        logger.info("Auto-expenses: created %d installment charges at %s UTC.", created, now_utc.isoformat())
    return created


# Returns the set of (subscription_id, date) tuples already present in expense_entries.
async def _existing_subscription_dates(session: AsyncSession, sub_ids: list[int]) -> set[tuple[int, date_type]]:
    if not sub_ids:
        return set()
    result = await session.execute(select(ExpenseEntry.subscription_id, ExpenseEntry.date).where(ExpenseEntry.subscription_id.in_(sub_ids)))
    return {(row[0], row[1]) for row in result.all()}


# Returns the set of (installment_id, date) tuples already present in expense_entries.
async def _existing_installment_dates(session: AsyncSession, inst_ids: list[int]) -> set[tuple[int, date_type]]:
    if not inst_ids:
        return set()
    result = await session.execute(select(ExpenseEntry.installment_id, ExpenseEntry.date).where(ExpenseEntry.installment_id.in_(inst_ids)))
    return {(row[0], row[1]) for row in result.all()}
