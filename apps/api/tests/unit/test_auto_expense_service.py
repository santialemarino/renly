from datetime import date

from app.services.auto_expense_service import (
    installment_cuotas_to_emit,
    subscription_dates_to_emit,
)
from app.utils.dates import (
    BILLING_CYCLE_ANNUAL,
    BILLING_CYCLE_BIWEEKLY,
    BILLING_CYCLE_MONTHLY,
    BILLING_CYCLE_QUARTERLY,
    BILLING_CYCLE_WEEKLY,
)

# --- subscription_dates_to_emit ---


class TestSubscriptionDatesToEmit:
    def test_no_emit_when_billing_in_future(self):
        result = subscription_dates_to_emit(date(2026, 5, 1), BILLING_CYCLE_MONTHLY, today=date(2026, 4, 26))
        assert result == []

    def test_single_emit_when_billing_today(self):
        result = subscription_dates_to_emit(date(2026, 4, 26), BILLING_CYCLE_MONTHLY, today=date(2026, 4, 26))
        assert result == [date(2026, 4, 26)]

    def test_back_fills_missed_monthly_cycles(self):
        # Subscription registered with next_billing_date 3 months in the past — back-fill all 3.
        result = subscription_dates_to_emit(date(2026, 1, 15), BILLING_CYCLE_MONTHLY, today=date(2026, 4, 26))
        assert result == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)]

    def test_clamps_day_and_drifts_after_short_month(self):
        # Subscriptions advance by chaining cursor → add_months(cursor, 1), so once
        # Jan 31 → Feb 28 clamps, subsequent cycles ride the new day-of-month (drift).
        # This is acceptable for v1 — installment cuotas don't drift because they
        # always derive from the original start_date.
        result = subscription_dates_to_emit(date(2026, 1, 31), BILLING_CYCLE_MONTHLY, today=date(2026, 4, 30))
        assert result == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 28), date(2026, 4, 28)]

    def test_annual_cycle(self):
        result = subscription_dates_to_emit(date(2024, 4, 26), BILLING_CYCLE_ANNUAL, today=date(2026, 4, 26))
        assert result == [date(2024, 4, 26), date(2025, 4, 26), date(2026, 4, 26)]

    def test_quarterly_cycle(self):
        result = subscription_dates_to_emit(date(2026, 1, 1), BILLING_CYCLE_QUARTERLY, today=date(2026, 7, 1))
        assert result == [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1)]

    def test_biweekly_cycle(self):
        result = subscription_dates_to_emit(date(2026, 4, 1), BILLING_CYCLE_BIWEEKLY, today=date(2026, 4, 26))
        assert result == [date(2026, 4, 1), date(2026, 4, 15)]

    def test_weekly_cycle(self):
        result = subscription_dates_to_emit(date(2026, 4, 19), BILLING_CYCLE_WEEKLY, today=date(2026, 4, 26))
        assert result == [date(2026, 4, 19), date(2026, 4, 26)]

    def test_unknown_cycle_falls_back_to_monthly(self):
        # Defensive: unknown cycle should still progress (not infinite-loop).
        result = subscription_dates_to_emit(date(2026, 3, 1), "lunar", today=date(2026, 4, 26))
        assert result == [date(2026, 3, 1), date(2026, 4, 1)]


# --- installment_cuotas_to_emit ---


class TestInstallmentCuotasToEmit:
    def test_no_emit_when_first_cuota_in_future(self):
        result = installment_cuotas_to_emit(
            start_date=date(2026, 5, 1),
            current_installment=1,
            installments_count=12,
            today=date(2026, 4, 26),
        )
        assert result == []

    def test_emits_first_cuota_on_start_date(self):
        result = installment_cuotas_to_emit(
            start_date=date(2026, 4, 26),
            current_installment=1,
            installments_count=12,
            today=date(2026, 4, 26),
        )
        assert result == [(1, date(2026, 4, 26))]

    def test_back_fills_missed_cuotas_when_registered_late(self):
        # Plan started 3 months ago, current_installment still 1 — back-fill cuotas 1..4.
        result = installment_cuotas_to_emit(
            start_date=date(2026, 1, 15),
            current_installment=1,
            installments_count=12,
            today=date(2026, 4, 26),
        )
        assert result == [
            (1, date(2026, 1, 15)),
            (2, date(2026, 2, 15)),
            (3, date(2026, 3, 15)),
            (4, date(2026, 4, 15)),
        ]

    def test_resumes_from_current_installment(self):
        # User manually set current_installment = 4 (already logged cuotas 1-3 elsewhere).
        # Today is far enough that cuotas 4 and 5 are due.
        result = installment_cuotas_to_emit(
            start_date=date(2026, 1, 15),
            current_installment=4,
            installments_count=12,
            today=date(2026, 5, 26),
        )
        assert result == [
            (4, date(2026, 4, 15)),
            (5, date(2026, 5, 15)),
        ]

    def test_caps_at_installments_count(self):
        # 3 cuotas total, plenty of time elapsed: emit all 3 and stop.
        result = installment_cuotas_to_emit(
            start_date=date(2026, 1, 1),
            current_installment=1,
            installments_count=3,
            today=date(2027, 1, 1),
        )
        assert result == [
            (1, date(2026, 1, 1)),
            (2, date(2026, 2, 1)),
            (3, date(2026, 3, 1)),
        ]

    def test_no_emit_when_already_fully_paid(self):
        # current_installment > installments_count: nothing to emit (lifecycle already flipped).
        result = installment_cuotas_to_emit(
            start_date=date(2026, 1, 1),
            current_installment=4,
            installments_count=3,
            today=date(2026, 12, 31),
        )
        assert result == []

    def test_clamps_cuota_day_for_short_months(self):
        # 31st cuota schedule clamps when months are shorter (Feb/Apr).
        result = installment_cuotas_to_emit(
            start_date=date(2026, 1, 31),
            current_installment=1,
            installments_count=4,
            today=date(2026, 4, 30),
        )
        assert result == [
            (1, date(2026, 1, 31)),
            (2, date(2026, 2, 28)),
            (3, date(2026, 3, 31)),
            (4, date(2026, 4, 30)),
        ]
