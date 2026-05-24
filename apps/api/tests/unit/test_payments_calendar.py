from datetime import date
from decimal import Decimal

from app.models.payment_obligation import PaymentObligation
from app.services.payments_calendar_service import obligation_dates_in_window


def _obligation(*, recurrence: str | None, next_due_date: date) -> PaymentObligation:
    # Minimal in-memory PaymentObligation. We only exercise the projection helper,
    # so user_id / amount / currency / id are placeholders.
    return PaymentObligation(
        id=1,
        user_id=1,
        name="Test obligation",
        amount=Decimal("1000"),
        currency="ARS",
        next_due_date=next_due_date,
        recurrence=recurrence,
        is_active=True,
    )


# --- One-off obligations ---


class TestOneOffObligations:
    def test_anchor_inside_window_emits_once(self):
        o = _obligation(recurrence=None, next_due_date=date(2026, 5, 15))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31))
        assert result == [date(2026, 5, 15)]

    def test_anchor_before_window_emits_nothing(self):
        # One-off in April when viewing May: nothing to show.
        o = _obligation(recurrence=None, next_due_date=date(2026, 4, 15))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31))
        assert result == []

    def test_anchor_after_window_emits_nothing(self):
        o = _obligation(recurrence=None, next_due_date=date(2026, 6, 15))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31))
        assert result == []


# --- Recurring obligations ---


class TestRecurringObligations:
    def test_monthly_recurring_emits_every_month_in_window(self):
        # Anchor in Jan, viewing May — emits May 25 (Jan → Feb → Mar → Apr → May projection).
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 1, 25))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31))
        assert result == [date(2026, 5, 25)]

    def test_monthly_emits_in_each_consecutive_month(self):
        # Anchor in May, viewing a 3-month window — emits May, June, July.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 5, 25))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 7, 31))
        assert result == [date(2026, 5, 25), date(2026, 6, 25), date(2026, 7, 25)]

    def test_monthly_anchor_day_31_clamps_in_short_months_without_drift(self):
        # Anchor day 31: Jan 31 → Feb 28 → Mar 31 → Apr 30 → May 31 (no drift).
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 1, 31))
        # Window spans Jan-May so we observe the full progression.
        result = obligation_dates_in_window(o, date(2026, 1, 1), date(2026, 5, 31))
        assert result == [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 31),
            date(2026, 4, 30),
            date(2026, 5, 31),
        ]

    def test_bimonthly_recurring(self):
        # ABL-style bimonthly: anchor Jan 10, viewing Jan-Jun → Jan 10, Mar 10, May 10.
        o = _obligation(recurrence="bimonthly", next_due_date=date(2026, 1, 10))
        result = obligation_dates_in_window(o, date(2026, 1, 1), date(2026, 6, 30))
        assert result == [date(2026, 1, 10), date(2026, 3, 10), date(2026, 5, 10)]

    def test_quarterly_recurring(self):
        o = _obligation(recurrence="quarterly", next_due_date=date(2026, 1, 15))
        result = obligation_dates_in_window(o, date(2026, 1, 1), date(2026, 12, 31))
        assert result == [
            date(2026, 1, 15),
            date(2026, 4, 15),
            date(2026, 7, 15),
            date(2026, 10, 15),
        ]

    def test_annual_recurring(self):
        # Anchor 2026-03-20, viewing March 2028 → exactly one occurrence.
        o = _obligation(recurrence="annual", next_due_date=date(2026, 3, 20))
        result = obligation_dates_in_window(o, date(2028, 3, 1), date(2028, 3, 31))
        assert result == [date(2028, 3, 20)]

    def test_window_strictly_before_anchor_emits_nothing(self):
        # Recurring obligations don't walk backward — anchor=May, window=Mar yields nothing.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 5, 25))
        result = obligation_dates_in_window(o, date(2026, 3, 1), date(2026, 3, 31))
        assert result == []

    def test_unknown_recurrence_treated_as_one_off(self):
        # Defensive: a garbage recurrence value falls back to one-off semantics.
        o = _obligation(recurrence="weekly", next_due_date=date(2026, 5, 15))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31))
        assert result == [date(2026, 5, 15)]
