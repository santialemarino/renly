# Business logic for retroactive auto-generation of expense_entries from active
# subscriptions and installment plans. The daily scheduler job calls
# generate_auto_expenses(); each tick back-fills missed cycles up to today and
# is idempotent across re-runs (dedup-keyed on (source plan, date)).

import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.expense_entry import ExpenseEntry
from app.models.installment import Installment
from app.models.subscription import Subscription
from app.utils.dates import add_months, advance_by_cycle

logger = logging.getLogger(__name__)

SOURCE_SUBSCRIPTION = "subscription"
SOURCE_INSTALLMENT = "installment"


# Returns the list of cycle dates a subscription should have emitted up to and
# including today, given its current next_billing_date and billing cycle.
# Pure function — does not advance the subscription record itself.
def subscription_dates_to_emit(next_billing_date: date_type, billing_cycle: str, today: date_type) -> list[date_type]:
    dates: list[date_type] = []
    cursor = next_billing_date
    # Safety cap to avoid runaway loops on bad data (e.g. unknown cycle landing on the same day).
    while cursor <= today and len(dates) < 1000:
        dates.append(cursor)
        nxt = advance_by_cycle(cursor, billing_cycle)
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


# Auto-generates expense entries for all active subscriptions and installments.
# Loops retroactively per record so plans registered with past dates back-fill
# in one tick. Re-runs are no-ops thanks to (source plan, date) pre-check + the
# matching partial unique indexes on expense_entries.
# Returns the count of expense_entries created.
async def generate_auto_expenses(session: AsyncSession, *, today: date_type | None = None) -> int:
    today = today or date_type.today()

    sub_count = await _generate_subscription_expenses(session, today)
    inst_count = await _generate_installment_expenses(session, today)

    if sub_count or inst_count:
        await session.commit()
    return sub_count + inst_count


# Emits expense_entries for active subscriptions whose next_billing_date is at
# or before today, advancing each subscription's next_billing_date in lockstep.
async def _generate_subscription_expenses(session: AsyncSession, today: date_type) -> int:
    result = await session.execute(
        select(Subscription).where(
            Subscription.is_active.is_(True),
            Subscription.next_billing_date <= today,
        )
    )
    subscriptions = list(result.scalars().all())
    if not subscriptions:
        return 0

    sub_ids = [s.id for s in subscriptions]
    existing = await _existing_subscription_dates(session, sub_ids)

    created = 0
    for sub in subscriptions:
        dates = subscription_dates_to_emit(sub.next_billing_date, sub.billing_cycle, today)
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
        next_after = advance_by_cycle(dates[-1], sub.billing_cycle)
        sub.next_billing_date = next_after
        session.add(sub)

    if created:
        await session.flush()
        logger.info("Auto-expenses: created %d subscription charges through %s.", created, today)
    return created


# Emits expense_entries for active installment plans whose next cuota date is
# at or before today. Increments current_installment per cuota and flips
# is_active to False once the plan is fully paid.
async def _generate_installment_expenses(session: AsyncSession, today: date_type) -> int:
    result = await session.execute(select(Installment).where(Installment.is_active.is_(True)))
    installments = list(result.scalars().all())
    if not installments:
        return 0

    # Pre-filter: skip plans where the next cuota is in the future.
    pending = [
        i for i in installments if i.current_installment <= i.installments_count and add_months(i.start_date, i.current_installment - 1) <= today
    ]
    if not pending:
        return 0

    inst_ids = [i.id for i in pending]
    existing = await _existing_installment_dates(session, inst_ids)

    created = 0
    for inst in pending:
        cuotas = installment_cuotas_to_emit(
            inst.start_date,
            inst.current_installment,
            inst.installments_count,
            today,
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
        logger.info("Auto-expenses: created %d installment charges through %s.", created, today)
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
