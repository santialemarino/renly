from datetime import date

from app.services.payment_obligation_service import compute_obligation_advance

# --- compute_obligation_advance ---


class TestComputeObligationAdvance:
    def test_monthly_advances_one_month(self):
        # Monthly obligation due May 15 -> next due June 15.
        result = compute_obligation_advance(date(2026, 5, 15), "monthly", anchor_day=15)
        assert result == (date(2026, 6, 15), True)

    def test_bimonthly_advances_two_months(self):
        # ABL-style bimonthly: anchor Jan 10 -> next Mar 10.
        result = compute_obligation_advance(date(2026, 1, 10), "bimonthly", anchor_day=10)
        assert result == (date(2026, 3, 10), True)

    def test_quarterly_advances_three_months(self):
        result = compute_obligation_advance(date(2026, 1, 15), "quarterly", anchor_day=15)
        assert result == (date(2026, 4, 15), True)

    def test_annual_advances_twelve_months_with_anchor_day_31_clamp(self):
        # Annual obligation anchored Mar 31 -> next due same day next year (no drift).
        result = compute_obligation_advance(date(2026, 3, 31), "annual", anchor_day=31)
        assert result == (date(2027, 3, 31), True)

    def test_monthly_anchor_day_31_clamps_in_short_target_month(self):
        # Jan 31 monthly -> Feb 28 (clamped). anchor_day stays 31 for the NEXT advance.
        result = compute_obligation_advance(date(2026, 1, 31), "monthly", anchor_day=31)
        assert result == (date(2026, 2, 28), True)

    def test_monthly_anchor_day_31_no_drift_after_short_month(self):
        # Regression: prior to anchor_day, advancing from Feb 28 used cursor.day (28),
        # drifting subsequent advances to the 28th forever. With anchor_day=31, advancing
        # from Feb 28 correctly snaps back to Mar 31.
        result = compute_obligation_advance(date(2026, 2, 28), "monthly", anchor_day=31)
        assert result == (date(2026, 3, 31), True)

    def test_one_off_archives_and_keeps_next_due_date(self):
        # One-off: is_active flips to False. next_due_date is preserved (audit trail).
        result = compute_obligation_advance(date(2026, 5, 15), None, anchor_day=15)
        assert result == (date(2026, 5, 15), False)

    def test_unknown_recurrence_keeps_obligation_active_and_unchanged(self):
        # Defensive default: corrupt recurrence value doesn't disable the obligation.
        result = compute_obligation_advance(date(2026, 5, 15), "fortnightly", anchor_day=15)
        assert result == (date(2026, 5, 15), True)
