# The monitoring half of a pot: the grid its value series is measured on, and what counts as an
# overdue valuation. Everything here is pure — no database, no HTTP — so the rules can be tested
# without either.
#
# Cadence is an EXPECTATION, not a schedule. Nothing in Renly writes a snapshot because a pot asked
# for one; declaring a cadence only says how often the people who co-own it agreed it would be
# re-valued, and the two things that follow from that are the two things here: how far apart the
# series' points sit, and how old a valuation has to be before the pot is behind.
#
# 'ad_hoc' declares no rhythm, so such a pot is NEVER reported as overdue — there is nothing to be
# late against. It still gets a series, on the monthly grid, because a pot with no agreed rhythm
# still has a value that moves and monthly is the rhythm Renly's own auto-snapshots keep.

from dataclasses import dataclass
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from app.models.pot import PotCadence
from app.utils.dates import add_months

_DAYS_IN_WEEK = 7


# The grid a value series is bucketed on. Narrower than PotCadence on purpose: 'ad_hoc' is a
# statement about expectations and not about time, so it has no grid of its own and borrows monthly.
class PotSeriesInterval(StrEnum):
    monthly = "monthly"
    weekly = "weekly"


# What a pot is worth on a date, and how current that answer is.
#
# The two nulls mean different things and are deliberately separate fields. `nav` is null whenever the
# total cannot be stated IN FULL — an unvalued holding, an unconvertible one, or nothing to value at
# all — because a sum missing a term is not a smaller sum. `valued_as_of` is null only when there is no
# valuation date to state: nothing held, or something held that has never been valued. A pot whose
# holdings are all snapshotted but one of which cannot be converted has a real `valued_as_of` and no
# `nav`, and saying so is more useful than collapsing both into "unknown".
@dataclass(frozen=True)
class PotValuation:
    nav: Decimal | None
    valued_as_of: date_type | None
    is_stale: bool


# The grid a pot's series is measured on. Only 'weekly' changes it.
def series_interval(cadence: PotCadence) -> PotSeriesInterval:
    return PotSeriesInterval.weekly if cadence == PotCadence.weekly else PotSeriesInterval.monthly


# The period end strictly before `d`: the last day of the previous calendar month, or the Sunday
# before this one. Applying it to a period end always yields the previous period end, which is what
# makes walking backwards from an arbitrary date land on a stable grid after the first step.
#
# `weekday() + 1` needs no special case for Sunday, and a mutation sweep is what settled that: Monday
# is 0 so it steps back 1 day, and Sunday is 6 so it steps back a full 7 — which is exactly the
# "strictly before" the walk requires. A guard for Sunday was written first and was provably dead.
def _previous_period_end(d: date_type, interval: PotSeriesInterval) -> date_type:
    if interval == PotSeriesInterval.weekly:
        return d - timedelta(days=d.weekday() + 1)
    return d.replace(day=1) - timedelta(days=1)


# The last `count` dates a series is valued at, ascending, ending at `today`.
#
# The final point is `today` rather than the current period's end, because that period has not
# finished and its end is a date nothing can be valued at yet. Every earlier point is a real period
# boundary — a month's last day, or a week's Sunday — so a pot snapshotted on the rhythm Renly's own
# auto-snapshots keep has a figure at each of them, rather than reading one period behind because
# the grid happened to be anchored on whatever day of the month it is now.
def period_ends(today: date_type, interval: PotSeriesInterval, count: int) -> list[date_type]:
    ends: list[date_type] = []
    cursor = today
    while len(ends) < count:
        ends.append(cursor)
        cursor = _previous_period_end(cursor, interval)
    ends.reverse()
    return ends


# The oldest a valuation may be before the cadence considers the pot behind: one whole period back.
# A valuation exactly one period old is DUE, not late, which is why the comparison below is strict.
def _cadence_cutoff(cadence: PotCadence, today: date_type) -> date_type:
    if cadence == PotCadence.weekly:
        return today - timedelta(days=_DAYS_IN_WEEK)
    return add_months(today, -1)


# Whether the pot's valuation is overdue against its declared cadence.
#
# Three arguments rather than one, because "no date" has two different causes and only one of them is
# a problem: a pot holding NOTHING has no valuation and is not behind on anything, while a pot holding
# something nobody has ever valued is behind by definition — its value cannot be stated at all, so no
# contribution can be priced against it. `holds_anything` is what separates them.
#
# An 'ad_hoc' pot is never overdue: it declared no rhythm, so there is no standard to fail.
def is_valuation_overdue(*, cadence: PotCadence, valued_as_of: date_type | None, holds_anything: bool, today: date_type) -> bool:
    if cadence == PotCadence.ad_hoc or not holds_anything:
        return False
    if valued_as_of is None:
        return True
    return valued_as_of < _cadence_cutoff(cadence, today)
