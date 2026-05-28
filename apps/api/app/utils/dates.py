# Date helpers shared across services (statement periods, scheduler back-fill, etc.).

import calendar
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"

# Subscription billing cycles understood by the auto-generation scheduler.
BILLING_CYCLE_MONTHLY = "monthly"
BILLING_CYCLE_ANNUAL = "annual"
BILLING_CYCLE_QUARTERLY = "quarterly"
BILLING_CYCLE_BIWEEKLY = "biweekly"
BILLING_CYCLE_WEEKLY = "weekly"

# Upper bound for the cycle-tolerance window (Phase 3, follow-up 3b). Annual cycles would
# otherwise yield ±182 days, which is too loose for "this entry belongs to that cycle"
# semantics; 60 days caps the slack at roughly two months for any cycle.
MAX_TOLERANCE_DAYS = 60

# Payment obligation recurrence -> calendar-month step. Shared by the Payments Calendar
# forward/backward walkers, the expense->obligation auto-advance, and the liquidity helper.
OBLIGATION_MONTH_STEP: dict[str, int] = {
    "monthly": 1,
    "bimonthly": 2,
    "quarterly": 3,
    "annual": 12,
}


# Adds N calendar months to a date, clamping the day to the last valid day of the target month.
# Example: add_months(2026-01-31, 1) -> 2026-02-28 (or 2026-02-29 in leap years).
def add_months(d: date_type, months: int) -> date_type:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, min(d.day, last_day))


# Advances `d` by `months` calendar months and snaps the day to `anchor_day`,
# clamping when the target month is too short. The anchor lets repeated calls
# preserve the user's intended day-of-month even after a previous step clamped
# (e.g. a 31st-of-month subscription billed Jan 31 -> Feb 28 -> Mar 31, not Mar 28).
def add_months_anchored(d: date_type, months: int, anchor_day: int) -> date_type:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, min(anchor_day, last_day))


# Advances a date by one full billing cycle. Falls back to monthly for unknown cycles
# so the scheduler keeps progressing instead of looping forever.
# `anchor_day` is honoured by the day-of-month cycles (monthly / quarterly / annual)
# to prevent post-clamp drift; weekly / biweekly are date-arithmetic so the anchor is irrelevant.
def advance_by_cycle(d: date_type, cycle: str, *, anchor_day: int | None = None) -> date_type:
    day = anchor_day if anchor_day is not None else d.day
    if cycle == BILLING_CYCLE_MONTHLY:
        return add_months_anchored(d, 1, day)
    if cycle == BILLING_CYCLE_ANNUAL:
        return add_months_anchored(d, 12, day)
    if cycle == BILLING_CYCLE_QUARTERLY:
        return add_months_anchored(d, 3, day)
    if cycle == BILLING_CYCLE_BIWEEKLY:
        return d + timedelta(days=14)
    if cycle == BILLING_CYCLE_WEEKLY:
        return d + timedelta(days=7)
    return add_months_anchored(d, 1, day)


# Returns the +/- tolerance window (in days) for "this manual entry belongs to that cycle"
# matching (Phase 3, follow-up 3b). Computed as min(cycle_length_in_days // 2, MAX_TOLERANCE_DAYS):
# half the cycle's nominal length, capped so annual / quarterly cycles don't loosen the
# match window past two months. Examples: weekly -> 3, biweekly -> 7, monthly -> 15,
# quarterly -> 45, annual -> 60 (capped). Anchor_day is forwarded into advance_by_cycle
# so day-of-month cycles measure their length from a fixed-day reference; weekly /
# biweekly ignore the anchor by definition.
def cycle_tolerance_days(cycle: str, *, anchor_day: int | None = None) -> int:
    reference = date_type(2026, 1, 1)
    day = anchor_day if anchor_day is not None else reference.day
    nominal_length = (advance_by_cycle(reference, cycle, anchor_day=day) - reference).days
    return min(nominal_length // 2, MAX_TOLERANCE_DAYS)


# Inverse of advance_by_cycle — steps a date backward by one full billing cycle.
# Used by the Payments Calendar to project past PAID cycles inside the viewed window.
# Falls back to monthly for unknown cycles, matching the forward variant's defensive behaviour.
def step_back_by_cycle(d: date_type, cycle: str, *, anchor_day: int | None = None) -> date_type:
    day = anchor_day if anchor_day is not None else d.day
    if cycle == BILLING_CYCLE_MONTHLY:
        return add_months_anchored(d, -1, day)
    if cycle == BILLING_CYCLE_ANNUAL:
        return add_months_anchored(d, -12, day)
    if cycle == BILLING_CYCLE_QUARTERLY:
        return add_months_anchored(d, -3, day)
    if cycle == BILLING_CYCLE_BIWEEKLY:
        return d - timedelta(days=14)
    if cycle == BILLING_CYCLE_WEEKLY:
        return d - timedelta(days=7)
    return add_months_anchored(d, -1, day)


# Resolves a 1..31 day-of-month into a concrete date for the given year/month,
# clamping to the last valid day when the target month is shorter (e.g. day=31 in Feb 2025 -> 2025-02-28).
# Matches how every surveyed Argentine bank handles month-end closing / due days.
def resolve_day_in_month(day: int, year: int, month: int) -> date_type:
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, min(day, last_day))


# Returns the user-local calendar date corresponding to `now_utc` in the given IANA timezone.
# Falls back to UTC (with a logged warning) on missing or invalid timezone names so the scheduler
# can never crash on stale data — the worst case mirrors today's UTC-everywhere behaviour.
def today_in_timezone(now_utc: datetime, tz_name: str | None) -> date_type:
    name = tz_name or DEFAULT_TIMEZONE
    try:
        return now_utc.astimezone(ZoneInfo(name)).date()
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %r — falling back to UTC.", name)
        return now_utc.astimezone(UTC).date()


# Returns the user-local hour (0-23) corresponding to `now_utc` in the given IANA timezone.
# Used by the auto-expense scheduler to filter users whose local time matches the configured hour.
# Falls back to UTC on missing or invalid timezone names.
def local_hour_for_user(now_utc: datetime, tz_name: str | None) -> int:
    name = tz_name or DEFAULT_TIMEZONE
    try:
        return now_utc.astimezone(ZoneInfo(name)).hour
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %r — falling back to UTC.", name)
        return now_utc.astimezone(UTC).hour


# Computes a credit-card statement period from the card's closing_day and the period's closing date.
# Returns (period_start, period_end) with both bounds inclusive.
# Semantics: a statement is identified by its closing date. period_end IS that closing date
# (the closing day is the LAST day of its own statement). period_start = previous closing date + 1 day.
# Day-of-month overflow on the previous month is resolved by clamping to the last day of the target month.
# Example: closing_day=15, statement_closing_date=2026-03-15 -> ((Feb 16, 2026), (Mar 15, 2026)).
# Example: closing_day=31, statement_closing_date=2026-03-31 -> ((Mar 1, 2026), (Mar 31, 2026))
#          because Feb 2026 has only 28 days, so the previous closing was clamped to Feb 28 -> next day = Mar 1.
def compute_statement_period(closing_day: int, statement_closing_date: date_type) -> tuple[date_type, date_type]:
    prev_month_total = statement_closing_date.year * 12 + (statement_closing_date.month - 1) - 1
    prev_year, prev_month = divmod(prev_month_total, 12)
    prev_month += 1
    previous_closing = resolve_day_in_month(closing_day, prev_year, prev_month)
    period_start = previous_closing + timedelta(days=1)
    return period_start, statement_closing_date
