# Date helpers shared across services (statement periods, scheduler back-fill, etc.).

import calendar
from datetime import date as date_type
from datetime import timedelta

# Subscription billing cycles understood by the auto-generation scheduler.
BILLING_CYCLE_MONTHLY = "monthly"
BILLING_CYCLE_ANNUAL = "annual"
BILLING_CYCLE_QUARTERLY = "quarterly"
BILLING_CYCLE_BIWEEKLY = "biweekly"
BILLING_CYCLE_WEEKLY = "weekly"


# Adds N calendar months to a date, clamping the day to the last valid day of the target month.
# Example: add_months(2026-01-31, 1) -> 2026-02-28 (or 2026-02-29 in leap years).
def add_months(d: date_type, months: int) -> date_type:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, min(d.day, last_day))


# Advances a date by one full billing cycle. Falls back to monthly for unknown cycles
# so the scheduler keeps progressing instead of looping forever.
def advance_by_cycle(d: date_type, cycle: str) -> date_type:
    if cycle == BILLING_CYCLE_MONTHLY:
        return add_months(d, 1)
    if cycle == BILLING_CYCLE_ANNUAL:
        return add_months(d, 12)
    if cycle == BILLING_CYCLE_QUARTERLY:
        return add_months(d, 3)
    if cycle == BILLING_CYCLE_BIWEEKLY:
        return d + timedelta(days=14)
    if cycle == BILLING_CYCLE_WEEKLY:
        return d + timedelta(days=7)
    return add_months(d, 1)
