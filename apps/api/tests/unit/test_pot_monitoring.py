# The pure monitoring rules: the grid a value series sits on, and what counts as an overdue valuation.
#
# Everything here is a rule a person can be shown ("this pot is behind", "these are the last twelve
# months"), so every test names the rule rather than the function. The grid in particular has an
# invariant worth stating outright: it is generated backwards from today but must land on real
# calendar boundaries after the first step, or a pot snapshotted on the rhythm Renly's own
# auto-snapshots keep would read one period behind at every point.

from datetime import date, timedelta

import pytest

from app.domain.pot_monitoring import (
    PotSeriesInterval,
    is_valuation_overdue,
    period_ends,
    series_interval,
)
from app.models.pot import PotCadence


class TestSeriesInterval:
    def test_only_a_weekly_cadence_produces_a_weekly_grid(self):
        assert series_interval(PotCadence.weekly) == PotSeriesInterval.weekly
        assert series_interval(PotCadence.monthly) == PotSeriesInterval.monthly

    def test_an_ad_hoc_pot_is_plotted_monthly(self):
        # It declares no rhythm, so it has no grid of its own — and a pot with no agreed rhythm still
        # has a value that moves. Monthly is the rhythm the app itself keeps.
        assert series_interval(PotCadence.ad_hoc) == PotSeriesInterval.monthly


class TestPeriodEnds:
    def test_the_last_point_is_today_and_the_list_is_oldest_first(self):
        today = date(2026, 8, 29)
        points = period_ends(today, PotSeriesInterval.monthly, 4)
        assert points[-1] == today
        assert points == sorted(points)

    def test_monthly_points_are_month_ends_below_the_current_one(self):
        # The current period has not finished, so its end is a date nothing can be valued at yet;
        # every earlier point is a real boundary.
        assert period_ends(date(2026, 8, 29), PotSeriesInterval.monthly, 4) == [
            date(2026, 5, 31),
            date(2026, 6, 30),
            date(2026, 7, 31),
            date(2026, 8, 29),
        ]

    def test_a_month_end_today_does_not_repeat_itself_as_the_previous_point(self):
        # The walk steps STRICTLY before today, so landing on a boundary is not a duplicate.
        assert period_ends(date(2026, 7, 31), PotSeriesInterval.monthly, 3) == [
            date(2026, 5, 31),
            date(2026, 6, 30),
            date(2026, 7, 31),
        ]

    def test_february_is_not_assumed_to_have_thirty_days(self):
        assert period_ends(date(2024, 3, 15), PotSeriesInterval.monthly, 3) == [
            date(2024, 1, 31),
            date(2024, 2, 29),
            date(2024, 3, 15),
        ]

    @pytest.mark.parametrize(
        ("today", "previous_sunday"),
        [
            (date(2026, 8, 24), date(2026, 8, 23)),  # Monday
            (date(2026, 8, 29), date(2026, 8, 23)),  # Saturday
            (date(2026, 8, 30), date(2026, 8, 23)),  # Sunday — a whole week back, not zero days
        ],
    )
    def test_weekly_points_step_back_to_the_previous_sunday_from_any_weekday(self, today, previous_sunday):
        points = period_ends(today, PotSeriesInterval.weekly, 2)
        assert points == [previous_sunday, today]

    def test_every_weekly_point_below_today_is_a_sunday_seven_days_apart(self):
        points = period_ends(date(2026, 8, 26), PotSeriesInterval.weekly, 6)
        boundaries = points[:-1]
        assert all(p.weekday() == 6 for p in boundaries)
        assert all(b - a == timedelta(days=7) for a, b in zip(boundaries, boundaries[1:]))

    def test_asking_for_one_point_returns_today_alone(self):
        assert period_ends(date(2026, 8, 29), PotSeriesInterval.monthly, 1) == [date(2026, 8, 29)]

    def test_the_count_is_honoured_exactly(self):
        assert len(period_ends(date(2026, 8, 29), PotSeriesInterval.weekly, 52)) == 52


class TestValuationOverdue:
    TODAY = date(2026, 8, 29)

    def test_an_ad_hoc_pot_is_never_behind(self):
        # It declared no rhythm, so there is no standard to fail — however old the valuation is.
        assert is_valuation_overdue(cadence=PotCadence.ad_hoc, valued_as_of=date(2020, 1, 1), holds_anything=True, today=self.TODAY) is False

    def test_a_pot_holding_nothing_is_never_behind(self):
        # "No valuation" has two causes and only one is a problem. A pot holding nothing has nothing
        # to value, and telling its members it is overdue would be a demand they cannot satisfy.
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=None, holds_anything=False, today=self.TODAY) is False

    def test_a_pot_holding_something_nobody_has_ever_valued_IS_behind(self):
        # The other cause: its value cannot be stated at all, so no contribution can be priced
        # against it. That is the state the indicator exists to surface.
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=None, holds_anything=True, today=self.TODAY) is True

    def test_a_valuation_exactly_one_period_old_is_due_and_not_yet_late(self):
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=date(2026, 7, 29), holds_anything=True, today=self.TODAY) is False
        assert is_valuation_overdue(cadence=PotCadence.weekly, valued_as_of=date(2026, 8, 22), holds_anything=True, today=self.TODAY) is False

    def test_a_day_past_the_period_is_late(self):
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=date(2026, 7, 28), holds_anything=True, today=self.TODAY) is True
        assert is_valuation_overdue(cadence=PotCadence.weekly, valued_as_of=date(2026, 8, 21), holds_anything=True, today=self.TODAY) is True

    def test_the_two_cadences_disagree_about_the_same_date(self):
        # The whole point of the setting: three weeks old is fine monthly and long overdue weekly.
        three_weeks_ago = date(2026, 8, 8)
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=three_weeks_ago, holds_anything=True, today=self.TODAY) is False
        assert is_valuation_overdue(cadence=PotCadence.weekly, valued_as_of=three_weeks_ago, holds_anything=True, today=self.TODAY) is True

    def test_the_monthly_cutoff_is_a_calendar_month_and_not_thirty_days(self):
        # 31 January minus one month is 31 December, not 1 January: a valuation from 30 December is
        # late and one from 31 December is not, which a fixed 30-day window would get wrong both ways.
        end_of_january = date(2026, 1, 31)
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=date(2025, 12, 31), holds_anything=True, today=end_of_january) is False
        assert is_valuation_overdue(cadence=PotCadence.monthly, valued_as_of=date(2025, 12, 30), holds_anything=True, today=end_of_january) is True
