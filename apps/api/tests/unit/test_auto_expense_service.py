from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.expense_entry import ExpenseEntry
from app.models.subscription import Subscription
from app.services.auto_expense_service import (
    AUTO_EXPENSES_HOUR_LOCAL,
    _generate_subscription_expenses,
    _scan_cutoff,
    installment_cuotas_to_emit,
    subscription_dates_to_emit,
)
from app.utils.dates import (
    BILLING_CYCLE_ANNUAL,
    BILLING_CYCLE_BIWEEKLY,
    BILLING_CYCLE_MONTHLY,
    BILLING_CYCLE_QUARTERLY,
    BILLING_CYCLE_WEEKLY,
    local_hour_for_user,
    today_in_timezone,
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

    def test_snaps_back_to_anchor_day_after_short_month(self):
        # When anchor_day is supplied (or implicitly defaulted to next_billing_date.day),
        # short-month clamps don't poison subsequent cycles: Jan 31 -> Feb 28 -> Mar 31 -> Apr 30.
        result = subscription_dates_to_emit(date(2026, 1, 31), BILLING_CYCLE_MONTHLY, today=date(2026, 4, 30))
        assert result == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]

    def test_explicit_anchor_day_overrides_next_billing_date_day(self):
        # next_billing_date is Feb 28 (already clamped from a Jan 31 emit), but anchor_day = 31.
        # The next cycle should snap back to Mar 31, not Mar 28.
        result = subscription_dates_to_emit(
            date(2026, 2, 28),
            BILLING_CYCLE_MONTHLY,
            today=date(2026, 5, 31),
            anchor_day=31,
        )
        assert result == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]

    def test_anchor_day_ignored_for_weekly_cycle(self):
        # Weekly advances by literal days; anchor_day has no meaning here.
        result = subscription_dates_to_emit(
            date(2026, 4, 19),
            BILLING_CYCLE_WEEKLY,
            today=date(2026, 4, 26),
            anchor_day=15,
        )
        assert result == [date(2026, 4, 19), date(2026, 4, 26)]

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


# --- Timezone-aware eligibility (Step G) ---


class TestTimezoneAwareEligibility:
    """
    The hourly cron processes a user iff their local-hour-now equals AUTO_EXPENSES_HOUR_LOCAL.
    Combined with the existing back-fill loop and today_in_timezone, this gives the
    user-local day-boundary semantics. These tests exercise the primitives composed
    by _generate_subscription_expenses (filter + today_in_user_tz + back-fill).
    """

    def test_argentina_user_at_04_utc_is_eligible(self):
        # 04:00 UTC = 01:00 ART -> matches AUTO_EXPENSES_HOUR_LOCAL.
        now = datetime(2026, 5, 25, 4, 0, tzinfo=UTC)
        assert local_hour_for_user(now, "America/Argentina/Buenos_Aires") == AUTO_EXPENSES_HOUR_LOCAL

    def test_argentina_user_at_01_utc_is_not_eligible(self):
        # 01:00 UTC = 22:00 ART previous day -> not eligible.
        now = datetime(2026, 5, 25, 1, 0, tzinfo=UTC)
        assert local_hour_for_user(now, "America/Argentina/Buenos_Aires") != AUTO_EXPENSES_HOUR_LOCAL

    def test_utc_user_at_01_utc_is_eligible(self):
        now = datetime(2026, 5, 25, 1, 0, tzinfo=UTC)
        assert local_hour_for_user(now, "UTC") == AUTO_EXPENSES_HOUR_LOCAL

    def test_argentina_user_today_at_eligible_tick_is_yesterday_utc(self):
        # At 04:00 UTC May 25 (= 01:00 ART May 25), user's local today is May 25.
        # A subscription due May 25 fires here (correctly within user's May 25, not pre-May-25).
        now = datetime(2026, 5, 25, 4, 0, tzinfo=UTC)
        user_today = today_in_timezone(now, "America/Argentina/Buenos_Aires")
        next_billing = date(2026, 5, 25)
        # The pure helper produces a single emit for this date.
        emits = subscription_dates_to_emit(next_billing, BILLING_CYCLE_MONTHLY, user_today)
        assert emits == [date(2026, 5, 25)]

    def test_argentina_user_at_pre_local_midnight_does_not_emit_tomorrow(self):
        # 02:00 UTC May 25 = 23:00 ART May 24. User local today is still May 24.
        # A subscription due May 25 must NOT emit yet — back-fill returns empty.
        now = datetime(2026, 5, 25, 2, 0, tzinfo=UTC)
        user_today = today_in_timezone(now, "America/Argentina/Buenos_Aires")
        assert user_today == date(2026, 5, 24)
        next_billing = date(2026, 5, 25)
        emits = subscription_dates_to_emit(next_billing, BILLING_CYCLE_MONTHLY, user_today)
        assert emits == []

    def test_constant_value_is_one(self):
        # Documented invariant: auto-expenses fire at the user's local 01:00.
        assert AUTO_EXPENSES_HOUR_LOCAL == 1


# --- Cycle-proximity dedup in the back-fill loop ---


class TestSchedulerCycleDedup:
    def _session(self, subscriptions, linked_rows):
        # First execute() call loads active subscriptions, second loads linked expense
        # dates ((sub_id, date) rows) — mirror the service's two queries.
        subs_result = Mock()
        subs_result.scalars.return_value.all.return_value = subscriptions
        linked_result = Mock()
        linked_result.all.return_value = linked_rows
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[subs_result, linked_result])
        session.add = Mock()
        session.flush = AsyncMock()
        return session

    def _sub(self) -> Subscription:
        return Subscription(
            id=1,
            user_id=1,
            name="Netflix",
            amount=Decimal("5990"),
            currency="ARS",
            billing_cycle=BILLING_CYCLE_MONTHLY,
            next_billing_date=date(2026, 6, 30),
            anchor_day=30,
            is_active=True,
        )

    @pytest.mark.asyncio
    async def test_pre_paid_cycle_not_double_emitted_but_cursor_advances(self):
        # Audit P0 scenario: Jun 30 cycle pre-paid via a linked expense dated Jun 28.
        # The Jul 1 tick (04:00 UTC = 01:00 ART) must emit NOTHING for Jun 30, yet still
        # advance the cursor to Jul 30 and report the advance so the caller commits.
        sub = self._sub()
        session = self._session([sub], [(1, date(2026, 6, 28))])
        now_utc = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
        created, advanced = await _generate_subscription_expenses(session, now_utc, {1: "America/Argentina/Buenos_Aires"})
        assert created == 0
        assert advanced == 1
        added_entries = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], ExpenseEntry)]
        assert added_entries == []
        assert sub.next_billing_date == date(2026, 7, 30)

    @pytest.mark.asyncio
    async def test_unpaid_cycle_still_emitted(self):
        # Regression: no linked expenses -> the Jun 30 charge is emitted exactly as before.
        sub = self._sub()
        session = self._session([sub], [])
        now_utc = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
        created, advanced = await _generate_subscription_expenses(session, now_utc, {1: "America/Argentina/Buenos_Aires"})
        assert created == 1
        assert advanced == 1
        added_entries = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], ExpenseEntry)]
        assert [e.date for e in added_entries] == [date(2026, 6, 30)]
        assert added_entries[0].subscription_id == 1
        assert sub.next_billing_date == date(2026, 7, 30)

    @pytest.mark.asyncio
    async def test_exact_date_row_still_dedups(self):
        # Regression: the old exact-date dedup is subsumed — a scheduler row dated exactly
        # Jun 30 claims the Jun 30 cycle.
        sub = self._sub()
        session = self._session([sub], [(1, date(2026, 6, 30))])
        now_utc = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
        created, advanced = await _generate_subscription_expenses(session, now_utc, {1: "America/Argentina/Buenos_Aires"})
        assert created == 0
        assert advanced == 1
        assert sub.next_billing_date == date(2026, 7, 30)


class Test_ScanCutoff:
    # The SQL due-scan cutoff leads the UTC date by one day so it covers every user's local today.
    def test_cutoff_is_utc_date_plus_one(self):
        assert _scan_cutoff(datetime(2026, 7, 12, 3, 0, tzinfo=UTC)) == date(2026, 7, 13)
