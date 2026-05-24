from datetime import date

from app.utils.dates import (
    BILLING_CYCLE_ANNUAL,
    BILLING_CYCLE_BIWEEKLY,
    BILLING_CYCLE_MONTHLY,
    BILLING_CYCLE_QUARTERLY,
    BILLING_CYCLE_WEEKLY,
    add_months,
    add_months_anchored,
    advance_by_cycle,
    compute_statement_period,
    resolve_day_in_month,
)

# --- add_months ---


class TestAddMonths:
    def test_simple_forward(self):
        assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)

    def test_year_boundary(self):
        assert add_months(date(2026, 12, 5), 1) == date(2027, 1, 5)

    def test_clamps_jan_31_to_feb_28_non_leap(self):
        # 2026 is not a leap year — Feb has 28 days.
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_clamps_jan_31_to_feb_29_leap(self):
        # 2024 is a leap year — Feb has 29 days.
        assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_clamps_to_30_day_month(self):
        assert add_months(date(2026, 1, 31), 3) == date(2026, 4, 30)

    def test_zero_months_is_noop(self):
        assert add_months(date(2026, 4, 26), 0) == date(2026, 4, 26)

    def test_full_year(self):
        assert add_months(date(2026, 4, 26), 12) == date(2027, 4, 26)

    def test_many_months(self):
        # 25 months from Jan 2026 = Feb 2028.
        assert add_months(date(2026, 1, 15), 25) == date(2028, 2, 15)


# --- advance_by_cycle ---


class TestAdvanceByCycle:
    def test_monthly(self):
        assert advance_by_cycle(date(2026, 4, 26), BILLING_CYCLE_MONTHLY) == date(2026, 5, 26)

    def test_annual(self):
        assert advance_by_cycle(date(2026, 4, 26), BILLING_CYCLE_ANNUAL) == date(2027, 4, 26)

    def test_quarterly(self):
        assert advance_by_cycle(date(2026, 4, 26), BILLING_CYCLE_QUARTERLY) == date(2026, 7, 26)

    def test_biweekly(self):
        assert advance_by_cycle(date(2026, 4, 26), BILLING_CYCLE_BIWEEKLY) == date(2026, 5, 10)

    def test_weekly(self):
        assert advance_by_cycle(date(2026, 4, 26), BILLING_CYCLE_WEEKLY) == date(2026, 5, 3)

    def test_unknown_cycle_falls_back_to_monthly(self):
        # Defensive: unknown cycle should still progress.
        assert advance_by_cycle(date(2026, 4, 26), "lunar") == date(2026, 5, 26)


# --- add_months_anchored ---


class TestAddMonthsAnchored:
    def test_uses_anchor_day_over_input_day(self):
        # Input date already clamped to Feb 28; anchor 31 wins for March.
        assert add_months_anchored(date(2026, 2, 28), 1, anchor_day=31) == date(2026, 3, 31)

    def test_clamps_anchor_day_to_short_month(self):
        # Anchor 31 in April clamps to 30.
        assert add_months_anchored(date(2026, 3, 31), 1, anchor_day=31) == date(2026, 4, 30)

    def test_anchor_day_smaller_than_input_day(self):
        # Anchor 5 should beat the input's day-of-month even when both fit.
        assert add_months_anchored(date(2026, 1, 20), 1, anchor_day=5) == date(2026, 2, 5)

    def test_three_months_with_anchor(self):
        # Useful for quarterly cycles: anchor 31 across Jan -> Apr clamps to Apr 30.
        assert add_months_anchored(date(2026, 1, 31), 3, anchor_day=31) == date(2026, 4, 30)


# --- advance_by_cycle with anchor_day ---


class TestAdvanceByCycleAnchored:
    def test_monthly_with_anchor_snaps_back_after_clamp(self):
        # Feb 28 (clamped previously) + monthly with anchor 31 = Mar 31, not Mar 28.
        assert advance_by_cycle(date(2026, 2, 28), BILLING_CYCLE_MONTHLY, anchor_day=31) == date(2026, 3, 31)

    def test_quarterly_with_anchor(self):
        assert advance_by_cycle(date(2026, 1, 31), BILLING_CYCLE_QUARTERLY, anchor_day=31) == date(2026, 4, 30)

    def test_annual_with_anchor(self):
        # 2027 is non-leap; anchor 29 on Feb clamps to 28.
        assert advance_by_cycle(date(2024, 2, 29), BILLING_CYCLE_ANNUAL, anchor_day=29) == date(2025, 2, 28)

    def test_weekly_ignores_anchor(self):
        # Weekly is pure date arithmetic — anchor_day must not interfere.
        assert advance_by_cycle(date(2026, 4, 19), BILLING_CYCLE_WEEKLY, anchor_day=15) == date(2026, 4, 26)

    def test_biweekly_ignores_anchor(self):
        assert advance_by_cycle(date(2026, 4, 1), BILLING_CYCLE_BIWEEKLY, anchor_day=15) == date(2026, 4, 15)

    def test_no_anchor_falls_back_to_input_day(self):
        # Backwards-compatible default — without anchor_day, behaviour matches the
        # pre-anchor implementation (uses d.day, drifts after clamps).
        assert advance_by_cycle(date(2026, 2, 28), BILLING_CYCLE_MONTHLY) == date(2026, 3, 28)


# --- resolve_day_in_month ---


class TestResolveDayInMonth:
    def test_normal_day_in_long_month(self):
        assert resolve_day_in_month(15, 2026, 3) == date(2026, 3, 15)

    def test_day_31_in_feb_non_leap(self):
        # Feb 2026 has 28 days.
        assert resolve_day_in_month(31, 2026, 2) == date(2026, 2, 28)

    def test_day_31_in_feb_leap(self):
        # Feb 2024 has 29 days.
        assert resolve_day_in_month(31, 2024, 2) == date(2024, 2, 29)

    def test_day_31_in_30_day_month(self):
        # April has 30 days.
        assert resolve_day_in_month(31, 2026, 4) == date(2026, 4, 30)

    def test_day_30_in_31_day_month_passes_through(self):
        assert resolve_day_in_month(30, 2026, 3) == date(2026, 3, 30)

    def test_day_1(self):
        assert resolve_day_in_month(1, 2026, 3) == date(2026, 3, 1)


# --- compute_statement_period ---


class TestComputeStatementPeriod:
    def test_closing_15_mid_month(self):
        # closing_day=15, statement closes Mar 15 -> period Feb 16 .. Mar 15.
        period_start, period_end = compute_statement_period(15, date(2026, 3, 15))
        assert period_start == date(2026, 2, 16)
        assert period_end == date(2026, 3, 15)

    def test_closing_31_in_long_month(self):
        # closing_day=31, statement closes Mar 31 -> previous closing was Feb 28 (2026 non-leap) -> period Mar 1 .. Mar 31.
        period_start, period_end = compute_statement_period(31, date(2026, 3, 31))
        assert period_start == date(2026, 3, 1)
        assert period_end == date(2026, 3, 31)

    def test_closing_31_in_short_month_clamps(self):
        # closing_day=31, current statement closes Feb 28 (2026 non-leap clamp) -> previous closing was Jan 31 -> period Feb 1 .. Feb 28.
        period_start, period_end = compute_statement_period(31, date(2026, 2, 28))
        assert period_start == date(2026, 2, 1)
        assert period_end == date(2026, 2, 28)

    def test_year_boundary(self):
        # closing_day=15, statement closes Jan 15, 2027 -> previous closing was Dec 15, 2026 -> period Dec 16, 2026 .. Jan 15, 2027.
        period_start, period_end = compute_statement_period(15, date(2027, 1, 15))
        assert period_start == date(2026, 12, 16)
        assert period_end == date(2027, 1, 15)

    def test_closing_1(self):
        # closing_day=1, statement closes Mar 1 -> previous closing was Feb 1 -> period Feb 2 .. Mar 1.
        period_start, period_end = compute_statement_period(1, date(2026, 3, 1))
        assert period_start == date(2026, 2, 2)
        assert period_end == date(2026, 3, 1)
