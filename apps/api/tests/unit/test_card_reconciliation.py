from datetime import date
from decimal import Decimal

from app.services.card_reconciliation_service import compute_reconciliation_difference, cumulative_balances_at

# --- compute_reconciliation_difference ---


class TestComputeReconciliationDifference:
    def test_positive_difference_creates_expense_side(self):
        # Bank says 1100, app computed 1000 -> 100 unaccounted (fees / taxes).
        assert compute_reconciliation_difference(Decimal("1100"), Decimal("1000")) == Decimal("100")

    def test_negative_difference_creates_income_side(self):
        # Bank says 900, app computed 1000 -> -100 (credit / refund the app missed).
        assert compute_reconciliation_difference(Decimal("900"), Decimal("1000")) == Decimal("-100")

    def test_zero_difference_means_no_adjustment(self):
        assert compute_reconciliation_difference(Decimal("1000"), Decimal("1000")) == Decimal("0")

    def test_two_decimal_precision_preserved(self):
        # Bank: 1234.56, computed: 1200.00 -> 34.56.
        assert compute_reconciliation_difference(Decimal("1234.56"), Decimal("1200.00")) == Decimal("34.56")

    def test_large_amount(self):
        assert compute_reconciliation_difference(Decimal("9999999.99"), Decimal("9999999.00")) == Decimal("0.99")

    def test_negative_computed_balance(self):
        # Overpaid bucket — computed_balance is negative (credit balance on card).
        # Bank says 0 (cleared the credit), app says -50 -> difference 50 (the credit was somehow consumed).
        assert compute_reconciliation_difference(Decimal("0"), Decimal("-50")) == Decimal("50")


# --- cumulative_balances_at (batched running-balance walk, P08 perf) ---


class TestCumulativeBalancesAt:
    def test_running_balance_across_closings_with_settlements(self):
        # Activity before the earliest closing feeds its base; a closing with no new expense
        # carries the running total; settlements net against expenses.
        expense_daily = [
            (date(2025, 12, 5), Decimal("20")),
            (date(2026, 1, 10), Decimal("100")),
            (date(2026, 2, 5), Decimal("50")),
            (date(2026, 3, 20), Decimal("30")),
        ]
        settlement_daily = [
            (date(2026, 2, 15), Decimal("40")),
            (date(2026, 4, 1), Decimal("10")),
        ]
        closings = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]

        result = cumulative_balances_at(closings, expense_daily, settlement_daily)

        assert result == {
            date(2026, 1, 31): Decimal("120"),  # 20 + 100
            date(2026, 2, 28): Decimal("130"),  # +50 - 40
            date(2026, 3, 31): Decimal("160"),  # +30, no settlement <= 3/31
            date(2026, 4, 30): Decimal("150"),  # -10 settlement, no new expense
        }

    def test_no_activity_yields_zero_at_every_closing(self):
        closings = [date(2026, 1, 31), date(2026, 2, 28)]
        result = cumulative_balances_at(closings, [], [])
        assert result == {date(2026, 1, 31): Decimal("0"), date(2026, 2, 28): Decimal("0")}
