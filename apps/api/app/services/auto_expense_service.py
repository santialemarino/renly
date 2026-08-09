# Business logic for retroactive auto-generation of expense_entries from active
# subscriptions and installment plans. The hourly scheduler job calls
# generate_auto_expenses(); each tick processes ONLY users whose local-time-now
# hour equals AUTO_EXPENSES_HOUR_LOCAL (= 1), so each user's charges fire at
# their own local 01:00. Per-user "today" is computed in the user's IANA tz.
# Idempotent across re-runs (dedup-keyed on (source plan, date)).

import logging
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.domain import claimed_installment_cuotas, claimed_subscription_cycles
from app.models.expense_entry import ExpenseEntry
from app.models.installment import Installment
from app.models.subscription import Subscription
from app.repositories import installment_repository, subscription_repository, user_settings_repository
from app.services import card_reconciliation_service
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


# Inclusive SQL cutoff for the due-scan: a user's local "today" can lead the UTC date by up to
# 14 hours (UTC+14), so scanning to utc_date + 1 day covers every user's local today. The exact
# per-user local-date comparison below still decides what actually emits.
def _scan_cutoff(now_utc: datetime) -> date_type:
    return now_utc.date() + timedelta(days=1)


# Auto-generates expense entries for active subscriptions and installments
# belonging to users whose local-time-now hour equals AUTO_EXPENSES_HOUR_LOCAL.
# Users with no stored timezone fall back to UTC. Idempotent on re-runs.
# Returns the count of expense_entries created.
async def generate_auto_expenses(session: AsyncSession, *, now_utc: datetime | None = None) -> int:
    now_utc = now_utc or datetime.now(UTC)

    user_timezones = await user_settings_repository.get_all_timezones(session)

    sub_created, sub_advanced = await _generate_subscription_expenses(session, now_utc, user_timezones)
    inst_created, inst_advanced = await _generate_installment_expenses(session, now_utc, user_timezones)

    # Commit also on emission-free ticks that advanced a cursor (pre-paid cycles): the
    # dedup suppresses the insert but the cursor catch-up must persist.
    if sub_created or inst_created or sub_advanced or inst_advanced:
        await session.commit()
    return sub_created + inst_created


# Emits expense_entries for active subscriptions belonging to eligible users
# (those whose local hour matches AUTO_EXPENSES_HOUR_LOCAL on this tick).
# Returns (created, advanced): entries inserted and plan cursors moved. The caller commits
# when either is non-zero — cycle-proximity dedup can advance a cursor past a pre-paid
# cycle without inserting anything, and that advance must still persist.
async def _generate_subscription_expenses(
    session: AsyncSession,
    now_utc: datetime,
    user_timezones: dict[int, str],
) -> tuple[int, int]:
    subscriptions = await subscription_repository.list_active_due(session, _scan_cutoff(now_utc))
    if not subscriptions:
        return 0, 0

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
        return 0, 0

    sub_ids = [s.id for s, _ in pending]
    existing = await _existing_subscription_dates(session, sub_ids)

    created = 0
    advanced = 0
    touched_buckets: dict[tuple[int, str], date_type] = {}
    for sub, today_for_user in pending:
        dates = subscription_dates_to_emit(
            sub.next_billing_date,
            sub.billing_cycle,
            today_for_user,
            anchor_day=sub.anchor_day,
        )
        if not dates:
            continue
        # Dedup by cycle proximity: every linked expense claims the cycle its own date binds
        # to under the same closest-cycle matching the manual-entry advance uses, so an
        # off-date pre-pay (e.g. an expense dated Jun 28 linked to the Jun 30 cycle) blocks
        # the back-fill from double-emitting that cycle. Exact-date rows claim their own
        # cycle, so this subsumes the old exact-date check; the partial UNIQUE INDEX on
        # (subscription_id, date) remains as a last-resort backstop.
        claimed = claimed_subscription_cycles(
            sub.next_billing_date,
            sub.billing_cycle,
            existing.get(sub.id, set()),
            anchor_day=sub.anchor_day,
        )
        for d in dates:
            if d in claimed:
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
            _track_card_bucket(touched_buckets, sub.credit_card_id, sub.currency, d)
            created += 1
        # Advance to the first cycle strictly after today — also when every emission was
        # deduped: that is exactly how a pre-paid cycle's frozen cursor catches up.
        next_after = advance_by_cycle(dates[-1], sub.billing_cycle, anchor_day=sub.anchor_day)
        sub.next_billing_date = next_after
        session.add(sub)
        advanced += 1

    if created:
        await session.flush()
        await _mark_touched_buckets_stale(session, touched_buckets)
        logger.info("Auto-expenses: created %d subscription charges at %s UTC.", created, now_utc.isoformat())
    return created, advanced


# Records that a scheduled charge landed in a card bucket, keeping the EARLIEST date seen per bucket.
# A statement goes stale once a charge dated on or before its period_end appears, so flagging from the
# earliest date covers every later charge in the same bucket with one call instead of one per row.
def _track_card_bucket(touched: dict[tuple[int, str], date_type], card_id: int | None, currency: str, charge_date: date_type) -> None:
    if card_id is None:
        return
    key = (card_id, currency)
    if key not in touched or charge_date < touched[key]:
        touched[key] = charge_date


# Flags every reconciliation whose recorded balance now includes a freshly emitted charge. The
# scheduler back-fills missed cycles, so it can insert a charge dated inside — or before — an already
# reconciled statement; without this the statement keeps rendering as reconciled while its figures no
# longer match. Does not commit: the caller owns the transaction.
async def _mark_touched_buckets_stale(session: AsyncSession, touched: dict[tuple[int, str], date_type]) -> None:
    for (card_id, currency), earliest in touched.items():
        await card_reconciliation_service.mark_stale_for_date(session, card_id, currency, earliest)


# Emits expense_entries for active installment plans belonging to eligible users.
# Returns (created, advanced): entries inserted and plan cursors moved. The caller commits
# when either is non-zero — cycle-proximity dedup can advance a cursor past a pre-paid
# cuota without inserting anything, and that advance must still persist.
async def _generate_installment_expenses(
    session: AsyncSession,
    now_utc: datetime,
    user_timezones: dict[int, str],
) -> tuple[int, int]:
    installments = await installment_repository.list_active_due(session, _scan_cutoff(now_utc))
    if not installments:
        return 0, 0

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
        return 0, 0

    inst_ids = [i.id for i, _ in pending]
    existing = await _existing_installment_dates(session, inst_ids)

    created = 0
    advanced = 0
    touched_buckets: dict[tuple[int, str], date_type] = {}
    for inst, today_for_user in pending:
        cuotas = installment_cuotas_to_emit(
            inst.start_date,
            inst.current_installment,
            inst.installments_count,
            today_for_user,
        )
        if not cuotas:
            continue
        # Dedup by cycle proximity — linked expenses claim the cuota INDEX their date binds
        # to (same closest-cuota matching as the manual-entry advance), so an off-date
        # pre-pay blocks the back-fill from double-emitting that cuota.
        claimed = claimed_installment_cuotas(
            inst.start_date,
            inst.installments_count,
            existing.get(inst.id, set()),
        )
        for idx, cuota_date in cuotas:
            if idx in claimed:
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
            _track_card_bucket(touched_buckets, inst.credit_card_id, inst.currency, cuota_date)
            created += 1
        # Advance the installment counter past the last emitted index (also when every
        # emission was deduped); flip the plan inactive once past the final installment.
        last_idx = cuotas[-1][0]
        inst.current_installment = last_idx + 1
        if inst.current_installment > inst.installments_count:
            inst.is_active = False
        session.add(inst)
        advanced += 1

    if created:
        await session.flush()
        await _mark_touched_buckets_stale(session, touched_buckets)
        logger.info("Auto-expenses: created %d installment charges at %s UTC.", created, now_utc.isoformat())
    return created, advanced


# Returns {subscription_id: set of linked expense dates} for every expense row linked to
# the given subscriptions. Unwindowed — cycle-proximity dedup binds each date to its
# closest cycle, so the plan's full linked history loads in one query before the loop.
async def _existing_subscription_dates(session: AsyncSession, sub_ids: list[int]) -> dict[int, set[date_type]]:
    if not sub_ids:
        return {}
    result = await session.execute(select(ExpenseEntry.subscription_id, ExpenseEntry.date).where(ExpenseEntry.subscription_id.in_(sub_ids)))
    grouped: dict[int, set[date_type]] = {}
    for sub_id, d in result.all():
        grouped.setdefault(sub_id, set()).add(d)
    return grouped


# Returns {installment_id: set of linked expense dates} for every expense row linked to
# the given installment plans. Unwindowed, one query — mirror of the subscription loader.
async def _existing_installment_dates(session: AsyncSession, inst_ids: list[int]) -> dict[int, set[date_type]]:
    if not inst_ids:
        return {}
    result = await session.execute(select(ExpenseEntry.installment_id, ExpenseEntry.date).where(ExpenseEntry.installment_id.in_(inst_ids)))
    grouped: dict[int, set[date_type]] = {}
    for inst_id, d in result.all():
        grouped.setdefault(inst_id, set()).add(d)
    return grouped
