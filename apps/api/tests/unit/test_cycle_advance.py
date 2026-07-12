from datetime import date

from app.domain import (
    claimed_installment_cuotas,
    claimed_subscription_cycles,
    closest_installment_cuota,
    closest_subscription_cycle,
    installment_link_advanced_cursor,
    subscription_link_advanced_cursor,
)
from app.services.auto_expense_service import subscription_dates_to_emit
from app.utils.dates import BILLING_CYCLE_MONTHLY, BILLING_CYCLE_WEEKLY

# --- closest_subscription_cycle ---


class TestClosestSubscriptionCycle:
    # Finds the cycle date nearest to a target manual-entry date. Walks forward or
    # backward from next_billing_date; the caller decides whether the returned cycle
    # is within tolerance and at-or-after the cursor.

    def test_target_equals_cursor_returns_cursor(self):
        cursor = date(2026, 6, 15)
        assert closest_subscription_cycle(cursor, BILLING_CYCLE_MONTHLY, cursor) == cursor

    def test_target_before_cursor_within_one_cycle_returns_past_cycle(self):
        # cursor = Jun 15, target = May 25 -> past cycle May 15 is closer (10 days)
        # than Jun 15 (21 days).
        assert closest_subscription_cycle(date(2026, 6, 15), BILLING_CYCLE_MONTHLY, date(2026, 5, 25)) == date(2026, 5, 15)

    def test_target_after_cursor_within_window_returns_cursor(self):
        # cursor = Jun 15, target = Jun 20 -> Jun 15 (5 days) closer than Jul 15 (25 days).
        assert closest_subscription_cycle(date(2026, 6, 15), BILLING_CYCLE_MONTHLY, date(2026, 6, 20)) == date(2026, 6, 15)

    def test_target_well_after_cursor_walks_forward(self):
        # cursor = Jun 15, target = Aug 15 -> Aug 15 is exactly the second cycle ahead.
        assert closest_subscription_cycle(date(2026, 6, 15), BILLING_CYCLE_MONTHLY, date(2026, 8, 15)) == date(2026, 8, 15)

    def test_anchor_day_31_walks_without_drift(self):
        # cursor = Mar 31 anchor=31, target = May 28 -> closest is May 31 (3 days)
        # not Apr 30 (28 days).
        result = closest_subscription_cycle(date(2026, 3, 31), BILLING_CYCLE_MONTHLY, date(2026, 5, 28), anchor_day=31)
        assert result == date(2026, 5, 31)

    def test_weekly_walks_in_seven_day_steps(self):
        # cursor = Jun 15 (Mon), target = Jun 24 -> cycle Jun 22 (2 days) closer than Jun 29 (5 days).
        assert closest_subscription_cycle(date(2026, 6, 15), BILLING_CYCLE_WEEKLY, date(2026, 6, 24)) == date(2026, 6, 22)

    def test_target_in_distant_past_walks_backward(self):
        # cursor = Jun 15, target = Jan 20 -> closest cycle Jan 15 (5 days) not Feb 15 (26 days).
        assert closest_subscription_cycle(date(2026, 6, 15), BILLING_CYCLE_MONTHLY, date(2026, 1, 20)) == date(2026, 1, 15)


# --- closest_installment_cuota ---


class TestClosestInstallmentCuota:
    def test_target_on_cuota_grid_returns_exact_match(self):
        # start = Jan 1, current = 1, count = 12, target = Apr 1 -> cuota 4.
        assert closest_installment_cuota(date(2026, 1, 1), 1, 12, date(2026, 4, 1)) == (4, date(2026, 4, 1))

    def test_target_between_cuotas_picks_closer(self):
        # start = Jan 1, target = Apr 20 -> cuota 4 (Apr 1, 19 days) closer than cuota 5 (May 1, 11 days).
        # Actually May 1 (11 days) is closer than Apr 1 (19 days), so cuota 5.
        assert closest_installment_cuota(date(2026, 1, 1), 1, 12, date(2026, 4, 20)) == (5, date(2026, 5, 1))

    def test_target_before_first_cuota_clamps_to_one(self):
        assert closest_installment_cuota(date(2026, 1, 1), 1, 12, date(2025, 12, 15)) == (1, date(2026, 1, 1))

    def test_target_after_last_cuota_clamps_to_count(self):
        # start = Jan 1, count = 3 -> final cuota Mar 1. Target Aug 1 still returns 3 (clamped).
        assert closest_installment_cuota(date(2026, 1, 1), 1, 3, date(2026, 8, 1)) == (3, date(2026, 3, 1))

    def test_returns_none_when_plan_fully_paid(self):
        # current_installment > installments_count means plan is done; can't advance further.
        assert closest_installment_cuota(date(2026, 1, 1), 13, 12, date(2026, 6, 15)) is None

    def test_short_month_clamp_does_not_skew_closest(self):
        # start = Jan 31 -> cuota 2 clamps to Feb 28. Target Feb 28 -> exact match on cuota 2.
        assert closest_installment_cuota(date(2026, 1, 31), 1, 6, date(2026, 2, 28)) == (2, date(2026, 2, 28))


# --- claimed_subscription_cycles ---


class TestClaimedSubscriptionCycles:
    def test_off_date_pre_pay_claims_its_cycle(self):
        # Expense dated Jun 28 binds to the Jun 30 cycle (2 days) not May 30 (29 days).
        claimed = claimed_subscription_cycles(date(2026, 6, 30), BILLING_CYCLE_MONTHLY, [date(2026, 6, 28)], anchor_day=30)
        assert claimed == {date(2026, 6, 30)}

    def test_exact_date_claims_itself(self):
        claimed = claimed_subscription_cycles(date(2026, 6, 30), BILLING_CYCLE_MONTHLY, [date(2026, 5, 30)], anchor_day=30)
        assert claimed == {date(2026, 5, 30)}

    def test_multiple_dates_claim_distinct_cycles(self):
        claimed = claimed_subscription_cycles(
            date(2026, 6, 30),
            BILLING_CYCLE_MONTHLY,
            [date(2026, 6, 28), date(2026, 5, 30)],
            anchor_day=30,
        )
        assert claimed == {date(2026, 6, 30), date(2026, 5, 30)}

    def test_empty_dates_claim_nothing(self):
        assert claimed_subscription_cycles(date(2026, 6, 30), BILLING_CYCLE_MONTHLY, [], anchor_day=30) == set()

    def test_double_emission_scenario_backfill_skips_pre_paid_cycle(self):
        # THE audit P0: cursor Jun 30, cycle pre-paid with an expense dated Jun 28, back-fill
        # runs Jul 1. dates_to_emit = [Jun 30]; the claim set blocks it -> nothing emitted.
        dates = subscription_dates_to_emit(date(2026, 6, 30), BILLING_CYCLE_MONTHLY, today=date(2026, 7, 1), anchor_day=30)
        assert dates == [date(2026, 6, 30)]
        claimed = claimed_subscription_cycles(date(2026, 6, 30), BILLING_CYCLE_MONTHLY, [date(2026, 6, 28)], anchor_day=30)
        assert [d for d in dates if d not in claimed] == []


# --- claimed_installment_cuotas ---


class TestClaimedInstallmentCuotas:
    def test_off_date_payment_claims_its_index(self):
        # Start Jan 15, expense Feb 13 -> cuota 2 (Feb 15, 2 days) not cuota 1 (29 days).
        assert claimed_installment_cuotas(date(2026, 1, 15), 12, [date(2026, 2, 13)]) == {2}

    def test_pre_start_date_claims_first_cuota(self):
        # Consistent with the create path's matcher: a pre-start link binds to cuota 1.
        assert claimed_installment_cuotas(date(2026, 1, 15), 12, [date(2025, 12, 20)]) == {1}

    def test_empty_dates_claim_nothing(self):
        assert claimed_installment_cuotas(date(2026, 1, 15), 12, []) == set()


# --- subscription_link_advanced_cursor ---


class TestSubscriptionLinkAdvancedCursor:
    def test_advanced_link_detected(self):
        # Link dated Jun 28 advanced the cursor Jun 30 -> Jul 30: it binds to Jun 30,
        # the cycle immediately before the current cursor.
        assert subscription_link_advanced_cursor(date(2026, 7, 30), BILLING_CYCLE_MONTHLY, date(2026, 6, 28), anchor_day=30) is True

    def test_historical_back_link_not_advanced(self):
        # Cursor Jul 30, link dated Mar 29 binds to Mar 30 — an old cycle, not Jun 30.
        assert subscription_link_advanced_cursor(date(2026, 7, 30), BILLING_CYCLE_MONTHLY, date(2026, 3, 29), anchor_day=30) is False

    def test_multi_jump_pre_pay_not_advanced(self):
        # Cursor still Jun 30 (multi-jump saved the link without advancing); the link
        # binds AT the cursor, not before it.
        assert subscription_link_advanced_cursor(date(2026, 6, 30), BILLING_CYCLE_MONTHLY, date(2026, 6, 28), anchor_day=30) is False

    def test_weekly_cycle(self):
        # Cursor Jun 22 weekly; link Jun 14 binds to Jun 15 = step-back cycle -> True.
        assert subscription_link_advanced_cursor(date(2026, 6, 22), BILLING_CYCLE_WEEKLY, date(2026, 6, 14)) is True

    def test_exact_cycle_midpoint_reverses(self):
        # Regression: an entry dated on the exact midpoint between two cycles (Apr 30 is
        # 15 days from both Apr 15 and May 15) advanced the cursor Apr 15 -> May 15 at
        # create time (forward-walk tie -> earlier cycle == cursor). The reverse must
        # recompute against the pre-advance cursor (Apr 15), not the post-advance cursor
        # (May 15) whose backward-walk tie would resolve to May 15 and wrongly return False.
        assert subscription_link_advanced_cursor(date(2026, 5, 15), BILLING_CYCLE_MONTHLY, date(2026, 4, 30), anchor_day=15) is True


# --- installment_link_advanced_cursor ---


class TestInstallmentLinkAdvancedCursor:
    def test_advanced_link_detected(self):
        # current=5 (cuotas 1-4 paid). Link dated Apr 3 binds to cuota 4 (Apr 1) = current-1.
        assert installment_link_advanced_cursor(date(2026, 1, 1), 5, 12, date(2026, 4, 3)) is True

    def test_historical_link_not_advanced(self):
        # Link dated Feb 1 binds to cuota 2, not cuota 4.
        assert installment_link_advanced_cursor(date(2026, 1, 1), 5, 12, date(2026, 2, 1)) is False

    def test_cursor_at_one_never_advanced(self):
        assert installment_link_advanced_cursor(date(2026, 1, 1), 1, 12, date(2026, 1, 1)) is False

    def test_fully_paid_final_cuota_detected(self):
        # current=13 on a 12-cuota plan: the final link (cuota 12, Dec 1) advanced it.
        assert installment_link_advanced_cursor(date(2026, 1, 1), 13, 12, date(2026, 12, 1)) is True
