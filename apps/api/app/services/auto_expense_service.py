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


# Returns (cuota_index, cuota_date) pairs an installment should have emitted up
# to and including today. Pure function — does not mutate the installment record.
# cuota_index is 1-based; cuota_date is start_date + (index - 1) months.
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
        # Advance the cuota counter past the last emitted cuota; flip the plan
        # inactive once we're past the final cuota.
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
