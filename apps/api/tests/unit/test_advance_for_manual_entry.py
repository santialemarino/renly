from datetime import date
from decimal import Decimal

from app.models.installment import Installment
from app.models.subscription import Subscription
from app.services.auto_expense_service import installment_cuotas_to_emit, subscription_dates_to_emit
from app.services.installment_service import compute_installment_advance_for_manual_entry
from app.services.subscription_service import compute_subscription_advance_for_manual_entry
from app.utils.dates import BILLING_CYCLE_ANNUAL, BILLING_CYCLE_MONTHLY, BILLING_CYCLE_WEEKLY, advance_by_cycle

# Pure decision helpers used by the soft-confirm preview endpoint and the actual
# write path in expense_service.create_expense (Phase 3, follow-up 3b). Both paths
# share the same predicate so the dialog and the eventual save can't disagree.


def _sub(
    *,
    next_billing_date: date,
    billing_cycle: str = BILLING_CYCLE_MONTHLY,
    anchor_day: int | None = None,
) -> Subscription:
    return Subscription(
        id=1,
        user_id=1,
        name="Netflix",
        amount=Decimal("10"),
        currency="USD",
        billing_cycle=billing_cycle,
        next_billing_date=next_billing_date,
        anchor_day=anchor_day if anchor_day is not None else next_billing_date.day,
    )


def _inst(
    *,
    start_date: date,
    current_installment: int = 1,
    installments_count: int = 12,
) -> Installment:
    return Installment(
        id=1,
        user_id=1,
        name="TV Samsung",
        total_amount=Decimal("1200"),
        installment_amount=Decimal("100"),
        currency="USD",
        installments_count=installments_count,
        current_installment=current_installment,
        start_date=start_date,
    )


# --- compute_subscription_advance_for_manual_entry ---


class TestComputeSubscriptionAdvanceForManualEntry:
    def test_exact_match_on_cursor_advances(self):
        # entry = cursor itself -> in tolerance + at-cursor; advances.
        sub = _sub(next_billing_date=date(2026, 6, 15))
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 6, 15))
        assert decision.would_advance is True
        assert decision.distance_days == 0
        assert decision.next_expected_date == date(2026, 6, 15)

    def test_in_tolerance_after_cursor_advances(self):
        # entry 10 days after cursor; monthly tolerance = 15 days.
        sub = _sub(next_billing_date=date(2026, 6, 15))
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 6, 25))
        assert decision.would_advance is True
        assert decision.distance_days == 10

    def test_back_dated_within_tolerance_does_not_advance(self):
        # entry 10 days BEFORE the cursor matches the prior May 15 cycle. In tolerance
        # by day-count, but back-dated -> do not advance.
        sub = _sub(next_billing_date=date(2026, 6, 15))
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 5, 25))
        assert decision.would_advance is False
        assert decision.next_expected_date == date(2026, 5, 15)

    def test_annual_cap_rejects_three_month_off_entry(self):
        # Annual tolerance caps at MAX_TOLERANCE_DAYS = 60, so 90 days off is rejected
        # despite half the cycle being ~182 days.
        sub = _sub(next_billing_date=date(2026, 6, 15), billing_cycle=BILLING_CYCLE_ANNUAL)
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 9, 14))
        assert decision.would_advance is False
        assert decision.distance_days == 91

    def test_weekly_tolerance_is_three_days(self):
        # Weekly cycle, entry 4 days after -> closest is the NEXT week's cycle (3 days
        # away) which IS within tolerance. Verifies the closest-cycle math, not just
        # the tolerance number.
        sub = _sub(next_billing_date=date(2026, 6, 15), billing_cycle=BILLING_CYCLE_WEEKLY)
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 6, 19))
        assert decision.would_advance is True
        assert decision.distance_days == 3

    def test_anchor_day_31_walks_without_drift(self):
        # cursor anchored on day 31 -> entry near May 31 should match May 31, not
        # drift back to Apr 30. Validates the closest helper honours anchor_day.
        sub = _sub(next_billing_date=date(2026, 3, 31), billing_cycle=BILLING_CYCLE_MONTHLY, anchor_day=31)
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 5, 30))
        assert decision.would_advance is True
        assert decision.next_expected_date == date(2026, 5, 31)


# --- compute_installment_advance_for_manual_entry ---


class TestComputeInstallmentAdvanceForManualEntry:
    def test_exact_match_on_first_cuota_advances(self):
        inst = _inst(start_date=date(2026, 1, 1), current_installment=1, installments_count=12)
        decision = compute_installment_advance_for_manual_entry(inst, date(2026, 1, 1))
        assert decision.would_advance is True
        assert decision.next_expected_date == date(2026, 1, 1)

    def test_in_tolerance_after_cursor_advances(self):
        # current = 3 -> cursor cuota is Mar 1; entry Mar 10 (9 days, within 15).
        inst = _inst(start_date=date(2026, 1, 1), current_installment=3, installments_count=12)
        decision = compute_installment_advance_for_manual_entry(inst, date(2026, 3, 10))
        assert decision.would_advance is True
        assert decision.next_expected_date == date(2026, 3, 1)

    def test_back_dated_before_cursor_does_not_advance(self):
        # current = 5 (Mar/Apr/May already advanced), entry Feb 1 -> matches cuota 2
        # which is < current cursor. Should not advance.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=5, installments_count=12)
        decision = compute_installment_advance_for_manual_entry(inst, date(2026, 2, 1))
        assert decision.would_advance is False
        assert decision.next_expected_date == date(2026, 2, 1)

    def test_fully_paid_plan_does_not_advance(self):
        # current_installment > count means the plan is done. closest_installment_cuota
        # returns None, advance never fires.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=13, installments_count=12)
        decision = compute_installment_advance_for_manual_entry(inst, date(2026, 6, 15))
        assert decision.would_advance is False

    def test_jumping_ahead_advances_past_skipped_cuotas(self):
        # User pays cuota 5 directly when current = 1 — the helper accepts (idx >= current)
        # and the caller will skip cuotas 1..4. Per the 3b plan "Multi-late entries get
        # one advance per save event" — this is the intended behaviour.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=1, installments_count=12)
        decision = compute_installment_advance_for_manual_entry(inst, date(2026, 5, 1))
        assert decision.would_advance is True
        assert decision.next_expected_date == date(2026, 5, 1)


# --- Scheduler doesn't double-emit after a manual-entry advance ---


class TestSchedulerNoDoubleEmitAfterManualAdvance:
    # Regression for the 3b plan's "manual-advanced cursor doesn't double-emit on the
    # next scheduler tick" guarantee. The math is already covered by the closest /
    # advance helpers individually; these two cases chain them through
    # subscription_dates_to_emit / installment_cuotas_to_emit to confirm the cursor
    # the scheduler reads is the post-advance one — so the matched cycle never
    # appears in the scheduler's emit list.

    def test_subscription_dates_to_emit_skips_manually_advanced_cycle(self):
        # Cursor at Jun 15 monthly. Manual entry on Jun 20 -> closest is Jun 15, in
        # tolerance, advances cursor one cycle to Jul 15. Scheduler ticking on Jun 25
        # sees cursor Jul 15 (future) -> emits nothing.
        sub = _sub(next_billing_date=date(2026, 6, 15))
        decision = compute_subscription_advance_for_manual_entry(sub, date(2026, 6, 20))
        assert decision.would_advance is True
        new_cursor = advance_by_cycle(decision.next_expected_date, sub.billing_cycle, anchor_day=sub.anchor_day)
        emit_dates = subscription_dates_to_emit(new_cursor, sub.billing_cycle, date(2026, 6, 25), anchor_day=sub.anchor_day)
        assert emit_dates == []

    def test_installment_cuotas_to_emit_skips_manually_advanced_cuota(self):
        # Plan with cuotas Jan/Feb/Mar/.../Dec. Cursor at cuota 3 (Mar 1). Manual entry
        # on Mar 5 -> closest cuota 3, in tolerance, advances current_installment to 4.
        # Scheduler ticking on Mar 10 sees cursor pointing at cuota 4 (Apr 1 > Mar 10)
        # -> emits nothing.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=3, installments_count=12)
        decision = compute_installment_advance_for_manual_entry(inst, date(2026, 3, 5))
        assert decision.would_advance is True
        # Simulate the post-advance cursor: current_installment becomes 4 (matched idx + 1).
        emit_pairs = installment_cuotas_to_emit(inst.start_date, 4, inst.installments_count, date(2026, 3, 10))
        assert emit_pairs == []
