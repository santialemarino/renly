from decimal import Decimal

from app.services.card_reconciliation_service import compute_reconciliation_difference

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
