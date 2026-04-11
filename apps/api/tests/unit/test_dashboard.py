from decimal import Decimal

from app.services.dashboard_service import compute_monthly_card_balances

# Rate map: 1 USD = 1200 ARS.
RATE_MAP = {
    "USD": Decimal("1"),
    "ARS": Decimal("1200"),
}


# --- compute_monthly_card_balances ---


class TestComputeMonthlyCardBalances:
    def test_single_card_single_currency(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 2, "USD", 50.0),
        ]
        settlements = [
            (1, 2026, 2, 80.0),
        ]
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            rate_map=RATE_MAP,
        )
        # Jan: 100 - 0 = 100. Feb: 100 + 50 - 80 = 70.
        assert result[(2026, 1)] == Decimal("100")
        assert result[(2026, 2)] == Decimal("70")

    def test_multi_card_multi_currency(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (2, 2026, 1, "ARS", 1200.0),  # 1200 ARS = 1 USD.
        ]
        settlements = []
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD", 2: "ARS"},
            target_currency="USD",
            rate_map=RATE_MAP,
        )
        # Card 1: 100 USD. Card 2: 1200 ARS → 1 USD. Total: 101 USD.
        assert result[(2026, 1)] == Decimal("101")

    def test_cumulative_across_months(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 3, "USD", 50.0),
        ]
        settlements = []
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            rate_map=RATE_MAP,
        )
        # Jan: 100. Mar: 100 + 50 = 150. Feb has no data, not in result.
        assert result[(2026, 1)] == Decimal("100")
        assert (2026, 2) not in result
        assert result[(2026, 3)] == Decimal("150")

    def test_settlement_exceeds_expenses(self):
        expenses = [
            (1, 2026, 1, "USD", 50.0),
        ]
        settlements = [
            (1, 2026, 1, 100.0),
        ]
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            rate_map=RATE_MAP,
        )
        # Overpayment: 50 - 100 = -50.
        assert result[(2026, 1)] == Decimal("-50")

    def test_empty_inputs(self):
        result = compute_monthly_card_balances(
            [],
            [],
            card_currencies={},
            target_currency="USD",
            rate_map=RATE_MAP,
        )
        assert result == {}

    def test_no_target_currency(self):
        # When no target currency, values pass through unconverted.
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 1, "ARS", 500.0),
        ]
        settlements = []
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency=None,
            rate_map=None,
        )
        # No conversion: 100 + 500 = 600 (meaningless but safe fallback).
        assert result[(2026, 1)] == Decimal("600")

    def test_foreign_expense_converted_to_card_then_target(self):
        # Card is ARS, expense in USD, target is ARS.
        expenses = [
            (1, 2026, 1, "USD", 10.0),  # 10 USD on an ARS card.
        ]
        settlements = []
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "ARS"},
            target_currency="ARS",
            rate_map=RATE_MAP,
        )
        # 10 USD → 12000 ARS (rate: 1 USD = 1200 ARS).
        assert result[(2026, 1)] == Decimal("12000")
