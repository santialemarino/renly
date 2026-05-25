from datetime import date
from decimal import Decimal

from app.models.payment_obligation import PaymentObligation
from app.services.payments_calendar_service import (
    obligation_dates_in_window,
    obligation_past_paid_dates_in_window,
)


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
        # Forward helper doesn't walk backward — anchor=May, window=Mar yields nothing.
        # Past-paid cycles surface via obligation_past_paid_dates_in_window instead.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 5, 25))
        result = obligation_dates_in_window(o, date(2026, 3, 1), date(2026, 3, 31))
        assert result == []

    def test_unknown_recurrence_treated_as_one_off(self):
        # Defensive: a garbage recurrence value falls back to one-off semantics.
        o = _obligation(recurrence="weekly", next_due_date=date(2026, 5, 15))
        result = obligation_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31))
        assert result == [date(2026, 5, 15)]


# --- Past-paid backward walker (Phase 3, Step E) ---


class TestPastPaidObligations:
    def test_monthly_one_payment_surfaces_prior_cycle(self):
        # User paid May → next_due_date advanced to June 15. Viewing May calendar
        # walks back ONE step (count=1) and lands on May 15 inside the window.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 6, 15))
        result = obligation_past_paid_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31), linked_expense_count=1)
        assert result == [date(2026, 5, 15)]

    def test_monthly_no_linked_expenses_emits_nothing(self):
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 6, 15))
        result = obligation_past_paid_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31), linked_expense_count=0)
        assert result == []

    def test_monthly_multiple_payments_walks_through_window(self):
        # User pre-paid 3 months in May → next_due_date = Aug 15. Viewing May–July
        # walks back 3 steps and surfaces May 15, June 15, July 15.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 8, 15))
        result = obligation_past_paid_dates_in_window(o, date(2026, 5, 1), date(2026, 7, 31), linked_expense_count=3)
        assert sorted(result) == [date(2026, 5, 15), date(2026, 6, 15), date(2026, 7, 15)]

    def test_walk_stops_when_cursor_exits_window(self):
        # 5 linked payments but only July is inside the August view: stop after July.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 12, 15))
        result = obligation_past_paid_dates_in_window(o, date(2026, 8, 1), date(2026, 8, 31), linked_expense_count=5)
        # Walk: Nov 15 (skip, > Aug 31), Oct 15 (skip), Sep 15 (skip), Aug 15 (append),
        # July 15 (< Aug 1, break).
        assert result == [date(2026, 8, 15)]

    def test_annual_anchor_day_31_clamps_across_short_month(self):
        # Annual obligation anchored Mar 31 → next_due_date already 2027-03-31.
        # One paid step backward → 2026-03-31 (no drift across short months).
        o = _obligation(recurrence="annual", next_due_date=date(2027, 3, 31))
        result = obligation_past_paid_dates_in_window(o, date(2026, 3, 1), date(2026, 3, 31), linked_expense_count=1)
        assert result == [date(2026, 3, 31)]

    def test_one_off_never_backward_walks(self):
        # One-off obligations get archived on payment — they don't backward-walk.
        o = _obligation(recurrence=None, next_due_date=date(2026, 6, 15))
        result = obligation_past_paid_dates_in_window(o, date(2026, 5, 1), date(2026, 5, 31), linked_expense_count=1)
        assert result == []
