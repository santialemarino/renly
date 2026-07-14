from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import CalendarItem, CardBucketBalance
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseEntry
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.services import payments_calendar_service
from app.services.payments_calendar_service import (
    _to_response,
    installment_past_paid_cuotas_in_window,
    obligation_dates_in_window,
    obligation_past_paid_cycles_in_window,
    subscription_past_paid_cycles_in_window,
)


def _obligation(
    *,
    recurrence: str | None,
    next_due_date: date,
    anchor_day: int | None = None,
) -> PaymentObligation:
    # Minimal in-memory PaymentObligation. We only exercise the projection helper,
    # so user_id / amount / currency / id are placeholders.
    # anchor_day defaults to next_due_date.day, matching the create-obligation auto-derive.
    return PaymentObligation(
        id=1,
        user_id=1,
        name="Test obligation",
        amount=Decimal("1000"),
        currency="ARS",
        next_due_date=next_due_date,
        anchor_day=anchor_day if anchor_day is not None else next_due_date.day,
        recurrence=recurrence,
        is_active=True,
    )


def _expense(
    *,
    date_val: date,
    amount: Decimal = Decimal("1000"),
    currency: str = "ARS",
) -> ExpenseEntry:
    # Minimal in-memory ExpenseEntry for the past-paid pairing tests. user_id and
    # payment_obligation_id are placeholders — the pairing helper consumes only date,
    # amount, and currency.
    return ExpenseEntry(
        id=1,
        user_id=1,
        date=date_val,
        amount=amount,
        currency=currency,
        source="manual",
        payment_obligation_id=1,
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
        # Past-paid cycles surface via obligation_past_paid_cycles_in_window instead.
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
    def test_monthly_one_payment_surfaces_prior_cycle_with_expense_data(self):
        # User paid May → next_due_date advanced to June 15. Viewing May calendar
        # walks back ONE step and pairs with the single linked expense.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 6, 15))
        e = _expense(date_val=date(2026, 5, 20), amount=Decimal("480"), currency="USD")
        result = obligation_past_paid_cycles_in_window(o, date(2026, 5, 1), date(2026, 5, 31), [e])
        assert result == [(date(2026, 5, 15), e)]

    def test_monthly_no_linked_expenses_emits_nothing(self):
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 6, 15))
        result = obligation_past_paid_cycles_in_window(o, date(2026, 5, 1), date(2026, 5, 31), [])
        assert result == []

    def test_monthly_multiple_payments_pair_newest_first(self):
        # User pre-paid 3 months → next_due_date = Aug 15. Viewing May-July. Linked
        # expenses sorted DESC by date so backward step `i` pairs with linked[i].
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 8, 15))
        e_july = _expense(date_val=date(2026, 7, 1), amount=Decimal("300"))
        e_june = _expense(date_val=date(2026, 6, 1), amount=Decimal("200"))
        e_may = _expense(date_val=date(2026, 5, 1), amount=Decimal("100"))
        result = obligation_past_paid_cycles_in_window(o, date(2026, 5, 1), date(2026, 7, 31), [e_july, e_june, e_may])
        # Backward walk emits July 15 → June 15 → May 15, each paired with the linked
        # expense at the same step index (newest cycle with newest expense).
        assert result == [
            (date(2026, 7, 15), e_july),
            (date(2026, 6, 15), e_june),
            (date(2026, 5, 15), e_may),
        ]

    def test_walk_stops_when_cursor_exits_window(self):
        # 5 linked payments but only August is inside the August view.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 12, 15))
        e_nov = _expense(date_val=date(2026, 11, 1))
        e_oct = _expense(date_val=date(2026, 10, 1))
        e_sep = _expense(date_val=date(2026, 9, 1))
        e_aug = _expense(date_val=date(2026, 8, 1), amount=Decimal("777"))
        e_jul = _expense(date_val=date(2026, 7, 1))
        result = obligation_past_paid_cycles_in_window(o, date(2026, 8, 1), date(2026, 8, 31), [e_nov, e_oct, e_sep, e_aug, e_jul])
        # Walk: Nov 15 (skip, > Aug 31), Oct 15 (skip), Sep 15 (skip), Aug 15 (append
        # paired with e_aug — step index 3), July 15 (< Aug 1, break).
        assert result == [(date(2026, 8, 15), e_aug)]

    def test_annual_anchor_day_31_clamps_across_short_month(self):
        # Annual obligation anchored Mar 31 → next_due_date already 2027-03-31.
        # One paid step backward → 2026-03-31 (no drift across short months).
        o = _obligation(recurrence="annual", next_due_date=date(2027, 3, 31))
        e = _expense(date_val=date(2026, 3, 30))
        result = obligation_past_paid_cycles_in_window(o, date(2026, 3, 1), date(2026, 3, 31), [e])
        assert result == [(date(2026, 3, 31), e)]

    def test_one_off_never_backward_walks(self):
        # One-off obligations get archived on payment — they don't backward-walk.
        o = _obligation(recurrence=None, next_due_date=date(2026, 6, 15))
        e = _expense(date_val=date(2026, 5, 20))
        result = obligation_past_paid_cycles_in_window(o, date(2026, 5, 1), date(2026, 5, 31), [e])
        assert result == []

    def test_paired_expense_amount_is_independent_of_obligation_amount(self):
        # The obligation says 1000 ARS but the linked expense was 1200 USD. The pair
        # must carry the EXPENSE's amount + currency, so editing the obligation later
        # doesn't rewrite past Paid badges on the calendar.
        o = _obligation(recurrence="monthly", next_due_date=date(2026, 6, 15))
        e = _expense(date_val=date(2026, 5, 20), amount=Decimal("1200"), currency="USD")
        result = obligation_past_paid_cycles_in_window(o, date(2026, 5, 1), date(2026, 5, 31), [e])
        assert result == [(date(2026, 5, 15), e)]
        # Sanity: paired expense carries historical values, obligation keeps current ones.
        assert result[0][1].amount == Decimal("1200")
        assert result[0][1].currency == "USD"
        assert o.amount == Decimal("1000")
        assert o.currency == "ARS"


# --- Router-level mapper (regression: is_paid must propagate to the response) ---


class TestToResponse:
    def test_is_paid_true_propagates_to_response(self):
        # Regression: prior to this test the `is_paid` flag was set on the domain
        # CalendarItem but not declared on PaymentsCalendarItemResponse, so the field
        # was silently dropped and the frontend Paid badge never rendered.
        item = CalendarItem(
            type="obligation",
            date=date(2026, 5, 15),
            name="ABL",
            amount=Decimal("1000"),
            currency="ARS",
            source_id=1,
            is_paid=True,
        )
        resp = _to_response(item, target_currency=None, lookup=None)
        assert resp.is_paid is True

    def test_is_paid_defaults_false_when_unset(self):
        item = CalendarItem(
            type="obligation",
            date=date(2026, 5, 15),
            name="ABL",
            amount=Decimal("1000"),
            currency="ARS",
            source_id=1,
        )
        resp = _to_response(item, target_currency=None, lookup=None)
        assert resp.is_paid is False

    def test_is_paid_false_for_non_obligation_events(self):
        item = CalendarItem(
            type="subscription",
            date=date(2026, 5, 15),
            name="Netflix",
            amount=Decimal("5990"),
            currency="ARS",
            source_id=1,
        )
        resp = _to_response(item, target_currency=None, lookup=None)
        assert resp.is_paid is False

    def test_linked_expense_id_propagates_to_response(self):
        # Regression: prior to round-2 follow-up, linked_expense_id wasn't propagated
        # by the router mapper — the frontend would have no way to open the linked
        # expense's edit dialog from a Paid badge click.
        item = CalendarItem(
            type="obligation",
            date=date(2026, 5, 15),
            name="ABL",
            amount=Decimal("1000"),
            currency="ARS",
            source_id=1,
            is_paid=True,
            linked_expense_id=42,
        )
        resp = _to_response(item, target_currency=None, lookup=None)
        assert resp.linked_expense_id == 42

    def test_linked_expense_id_defaults_none_when_unset(self):
        item = CalendarItem(
            type="card_due",
            date=date(2026, 5, 15),
            name="Visa",
            amount=Decimal("50000"),
            currency="ARS",
            source_id=1,
        )
        resp = _to_response(item, target_currency=None, lookup=None)
        assert resp.linked_expense_id is None


# --- Subscription past-paid backward walker (round-2 follow-up) ---


def _subscription(
    *,
    billing_cycle: str,
    next_billing_date: date,
    anchor_day: int | None = None,
) -> Subscription:
    # Minimal in-memory Subscription. The walker exercises only billing_cycle +
    # next_billing_date + anchor_day; the rest are placeholders.
    return Subscription(
        id=1,
        user_id=1,
        name="Netflix",
        amount=Decimal("5990"),
        currency="ARS",
        billing_cycle=billing_cycle,
        next_billing_date=next_billing_date,
        anchor_day=anchor_day if anchor_day is not None else next_billing_date.day,
        is_active=True,
    )


class TestSubscriptionPastPaidCycles:
    def test_no_linked_expenses_emits_nothing(self):
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 6, 15))
        assert subscription_past_paid_cycles_in_window(sub, date(2026, 5, 1), date(2026, 5, 31), []) == []

    def test_monthly_one_past_cycle_with_exact_date_expense(self):
        # Regression: scheduler-emitted row dated exactly on the cycle keeps working.
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 6, 15))
        e = _expense(date_val=date(2026, 5, 15), amount=Decimal("5990"))
        result = subscription_past_paid_cycles_in_window(sub, date(2026, 5, 1), date(2026, 5, 31), [e])
        assert result == [(date(2026, 5, 15), e)]

    def test_off_cycle_payment_still_marks_cycle_paid(self):
        # THE audit P1: Netflix Mar 31 cycle paid Mar 29 -> cursor advanced to Apr 30
        # (anchor 31). March must show the Mar 31 cycle as paid, carrying the expense.
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 4, 30), anchor_day=31)
        e = _expense(date_val=date(2026, 3, 29), amount=Decimal("5990"))
        result = subscription_past_paid_cycles_in_window(sub, date(2026, 3, 1), date(2026, 3, 31), [e])
        assert result == [(date(2026, 3, 31), e)]

    def test_skips_cycle_whose_link_binds_elsewhere(self):
        # Replaces test_monthly_skips_cycle_without_matching_expense: a January-dated link
        # binds to the Jan 15 cycle, so viewing May emits nothing — the link can't badge
        # May 15 (naive positional pairing would have).
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 6, 15))
        result = subscription_past_paid_cycles_in_window(sub, date(2026, 5, 1), date(2026, 5, 31), [_expense(date_val=date(2026, 1, 15))])
        assert result == []

    def test_multiple_off_date_payments_pair_newest_first(self):
        # Jul 15 exact, Jun 13 (binds Jun 15), May 17 (binds May 15) — all three badge.
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 8, 15))
        e_jul = _expense(date_val=date(2026, 7, 15))
        e_jun = _expense(date_val=date(2026, 6, 13))
        e_may = _expense(date_val=date(2026, 5, 17))
        result = subscription_past_paid_cycles_in_window(sub, date(2026, 5, 1), date(2026, 7, 31), [e_jul, e_jun, e_may])
        assert result == [(date(2026, 7, 15), e_jul), (date(2026, 6, 15), e_jun), (date(2026, 5, 15), e_may)]

    def test_pre_pay_at_cursor_not_badged_backward(self):
        # Multi-jump pre-pay: cursor still Jun 30, expense Jun 28 binds AT the cursor.
        # The backward walker must not badge anything — the forward walker owns Jun 30
        # (unpaid) until the scheduler advances the cursor.
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 6, 30), anchor_day=30)
        e = _expense(date_val=date(2026, 6, 28))
        assert subscription_past_paid_cycles_in_window(sub, date(2026, 6, 1), date(2026, 6, 30), [e]) == []

    def test_anchor_day_31_no_drift_on_backward_walk(self):
        # Day-31 subscription: May 31 cursor walks back Apr 30 (clamped) then Mar 31.
        sub = _subscription(billing_cycle="monthly", next_billing_date=date(2026, 5, 31), anchor_day=31)
        e_apr = _expense(date_val=date(2026, 4, 30))
        e_mar = _expense(date_val=date(2026, 3, 31))
        result = subscription_past_paid_cycles_in_window(sub, date(2026, 3, 1), date(2026, 4, 30), [e_apr, e_mar])
        assert result == [(date(2026, 4, 30), e_apr), (date(2026, 3, 31), e_mar)]

    def test_weekly_cycle_walks_in_7_day_steps(self):
        sub = _subscription(billing_cycle="weekly", next_billing_date=date(2026, 5, 22))
        e_may15 = _expense(date_val=date(2026, 5, 15))
        e_may8 = _expense(date_val=date(2026, 5, 8))
        result = subscription_past_paid_cycles_in_window(sub, date(2026, 5, 1), date(2026, 5, 21), [e_may15, e_may8])
        assert result == [(date(2026, 5, 15), e_may15), (date(2026, 5, 8), e_may8)]


# --- Installment past-paid backward walker (round-2 follow-up) ---


def _installment(
    *,
    start_date: date,
    installments_count: int,
    current_installment: int,
) -> Installment:
    # Minimal in-memory Installment. The walker exercises start_date + current_installment +
    # installments_count; the rest are placeholders.
    return Installment(
        id=1,
        user_id=1,
        name="TV Samsung",
        total_amount=Decimal("120000"),
        installment_amount=Decimal("10000"),
        currency="ARS",
        installments_count=installments_count,
        start_date=start_date,
        current_installment=current_installment,
        is_active=True,
    )


class TestInstallmentPastPaidCuotas:
    def test_no_past_cuotas_when_current_installment_is_one(self):
        inst = _installment(start_date=date(2026, 1, 15), installments_count=12, current_installment=1)
        e = _expense(date_val=date(2026, 1, 15))
        assert installment_past_paid_cuotas_in_window(inst, date(2026, 1, 1), date(2026, 1, 31), [e]) == []

    def test_one_past_cuota_exact_date(self):
        inst = _installment(start_date=date(2026, 1, 15), installments_count=12, current_installment=2)
        e = _expense(date_val=date(2026, 1, 15), amount=Decimal("10000"))
        result = installment_past_paid_cuotas_in_window(inst, date(2026, 1, 1), date(2026, 1, 31), [e])
        assert result == [(1, date(2026, 1, 15), e)]

    def test_off_date_payment_marks_cuota_paid(self):
        # Cuota 2 (Apr 10) paid Apr 8 -> counter advanced to 3. April must badge cuota 2.
        inst = _installment(start_date=date(2026, 3, 10), installments_count=12, current_installment=3)
        e2 = _expense(date_val=date(2026, 4, 8))
        e1 = _expense(date_val=date(2026, 3, 10))
        result = installment_past_paid_cuotas_in_window(inst, date(2026, 3, 1), date(2026, 4, 30), [e2, e1])
        assert result == [(1, date(2026, 3, 10), e1), (2, date(2026, 4, 10), e2)]

    def test_skips_cuota_without_bound_expense(self):
        inst = _installment(start_date=date(2026, 1, 15), installments_count=12, current_installment=2)
        assert installment_past_paid_cuotas_in_window(inst, date(2026, 1, 1), date(2026, 1, 31), []) == []

    def test_pre_pay_bound_at_cursor_not_badged(self):
        # current=2; a pre-pay dated Feb 13 binds to cuota 2 (= the cursor) — forward
        # walker territory, so the backward walker emits nothing.
        inst = _installment(start_date=date(2026, 1, 15), installments_count=12, current_installment=2)
        e = _expense(date_val=date(2026, 2, 13))
        assert installment_past_paid_cuotas_in_window(inst, date(2026, 1, 1), date(2026, 2, 28), [e]) == []

    def test_only_emits_cuotas_inside_window(self):
        inst = _installment(start_date=date(2026, 1, 10), installments_count=12, current_installment=6)
        e_apr = _expense(date_val=date(2026, 4, 10))
        result = installment_past_paid_cuotas_in_window(inst, date(2026, 4, 1), date(2026, 4, 30), [e_apr])
        assert result == [(4, date(2026, 4, 10), e_apr)]

    def test_fully_paid_installment_walks_through_all_cuotas(self):
        inst = _installment(start_date=date(2026, 1, 15), installments_count=3, current_installment=4)
        e3 = _expense(date_val=date(2026, 3, 15))
        e2 = _expense(date_val=date(2026, 2, 15))
        e1 = _expense(date_val=date(2026, 1, 15))
        result = installment_past_paid_cuotas_in_window(inst, date(2026, 1, 1), date(2026, 3, 31), [e3, e2, e1])
        assert result == [(1, date(2026, 1, 15), e1), (2, date(2026, 2, 15), e2), (3, date(2026, 3, 15), e3)]

    def test_short_month_clamp_for_day_31_start_no_drift(self):
        # start Jan 31: cuota dates Jan 31 / Feb 28 / Mar 31 (recomputed from start_date).
        inst = _installment(start_date=date(2026, 1, 31), installments_count=12, current_installment=4)
        e_mar = _expense(date_val=date(2026, 3, 31))
        e_feb = _expense(date_val=date(2026, 2, 28))
        e_jan = _expense(date_val=date(2026, 1, 31))
        result = installment_past_paid_cuotas_in_window(inst, date(2026, 1, 1), date(2026, 3, 31), [e_mar, e_feb, e_jan])
        assert result == [(1, date(2026, 1, 31), e_jan), (2, date(2026, 2, 28), e_feb), (3, date(2026, 3, 31), e_mar)]


# --- card_due paid-marking ---


USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


class TestCardDuePaidMarking:
    def _patch(self, monkeypatch, *, snapshot: Decimal, settled: Decimal) -> None:
        card = CreditCard(id=1, user_id=1, name="Visa", closing_day=20, due_day=5, currency="ARS", is_active=True)
        monkeypatch.setattr(payments_calendar_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[card]))
        monkeypatch.setattr(
            payments_calendar_service.credit_card_service,
            "get_card_balances",
            AsyncMock(return_value={1: [CardBucketBalance(currency="ARS", balance=snapshot)]}),
        )
        monkeypatch.setattr(
            payments_calendar_service.card_reconciliation_service,
            "compute_bucket_balances_at",
            AsyncMock(return_value={(1, "ARS"): snapshot}),
        )
        self.settled_mock = AsyncMock(return_value=settled)
        monkeypatch.setattr(payments_calendar_service.card_reconciliation_repository, "sum_settlements_between", self.settled_mock)

    @pytest.mark.asyncio
    async def test_fully_settled_statement_is_paid(self, monkeypatch):
        # closing_day=20 > due_day=5, so June 5's bill is the May 20 statement. A 100,000
        # settlement dated inside (May 20, Jun 5] covers the 100,000 snapshot -> Paid.
        self._patch(monkeypatch, snapshot=Decimal("100000"), settled=Decimal("100000"))
        items = await payments_calendar_service._card_due_items(AsyncMock(), USER, date(2026, 6, 1), date(2026, 6, 30), 2026, 6)
        assert len(items) == 1
        assert items[0].type == "card_due"
        assert items[0].date == date(2026, 6, 5)
        assert items[0].amount == Decimal("100000")  # Frozen statement amount, not reduced.
        assert items[0].is_paid is True
        # Settlement window is exactly (closing, due].
        assert self.settled_mock.call_args.args[2:] == ("ARS", date(2026, 5, 20), date(2026, 6, 5))

    @pytest.mark.asyncio
    async def test_partial_settlement_stays_unpaid(self, monkeypatch):
        self._patch(monkeypatch, snapshot=Decimal("100000"), settled=Decimal("99999.99"))
        items = await payments_calendar_service._card_due_items(AsyncMock(), USER, date(2026, 6, 1), date(2026, 6, 30), 2026, 6)
        assert items[0].is_paid is False

    @pytest.mark.asyncio
    async def test_negative_snapshot_never_paid_and_skips_query(self, monkeypatch):
        # A credit balance is not a bill: no Paid badge, no settlements query.
        self._patch(monkeypatch, snapshot=Decimal("-50"), settled=Decimal("0"))
        items = await payments_calendar_service._card_due_items(AsyncMock(), USER, date(2026, 6, 1), date(2026, 6, 30), 2026, 6)
        assert items[0].is_paid is False
        self.settled_mock.assert_not_called()
