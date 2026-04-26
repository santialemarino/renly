from datetime import date

from app.utils.dates import (
    BILLING_CYCLE_ANNUAL,
    BILLING_CYCLE_BIWEEKLY,
    BILLING_CYCLE_MONTHLY,
    BILLING_CYCLE_QUARTERLY,
    BILLING_CYCLE_WEEKLY,
    add_months,
    advance_by_cycle,
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
