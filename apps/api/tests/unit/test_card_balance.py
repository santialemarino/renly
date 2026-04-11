from decimal import Decimal

from app.services.credit_card_service import compute_card_balances

# Rate map: 1 USD = 1200 ARS, 1 USD = 0.92 EUR.
RATE_MAP = {
    "USD": Decimal("1"),
    "ARS": Decimal("1200"),
    "EUR": Decimal("0.92"),
}


# --- compute_card_balances ---


class TestComputeCardBalances:
    def test_single_currency_no_conversion(self):
        # Card in USD, all expenses in USD.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"USD": 100.0}},
            settlement_sums={1: 30.0},
            rate_map=None,
        )
        bal = result[1]
        assert bal.balance == Decimal("70")
        assert bal.has_mixed_currencies is False

    def test_mixed_currencies_converts_to_card_currency(self):
        # Card in USD. Expenses: 100 USD + 1200 ARS (= 1 USD).
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"USD": 100.0, "ARS": 1200.0}},
            settlement_sums={1: 0.0},
            rate_map=RATE_MAP,
        )
        bal = result[1]
        assert bal.balance == Decimal("101")
        assert bal.has_mixed_currencies is True

    def test_foreign_only_marks_mixed(self):
        # Card in USD, but only ARS expenses.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"ARS": 2400.0}},
            settlement_sums={1: 0.0},
            rate_map=RATE_MAP,
        )
        bal = result[1]
        # 2400 ARS / 1200 = 2 USD.
        assert bal.balance == Decimal("2")
        assert bal.has_mixed_currencies is True

    def test_no_expenses_no_settlements(self):
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={},
            settlement_sums={},
            rate_map=None,
        )
        bal = result[1]
        assert bal.balance == Decimal("0")
        assert bal.has_mixed_currencies is False

    def test_settlement_exceeds_expenses(self):
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "ARS"},
            expense_grouped={1: {"ARS": 5000.0}},
            settlement_sums={1: 8000.0},
            rate_map=None,
        )
        bal = result[1]
        assert bal.balance == Decimal("-3000")
        assert bal.has_mixed_currencies is False

    def test_multiple_cards(self):
        # Card 1: USD card, only USD expenses. Card 2: ARS card, mixed expenses.
        result = compute_card_balances(
            card_ids=[1, 2],
            card_currencies={1: "USD", 2: "ARS"},
            expense_grouped={
                1: {"USD": 50.0},
                2: {"ARS": 10000.0, "USD": 10.0},
            },
            settlement_sums={1: 20.0, 2: 5000.0},
            rate_map=RATE_MAP,
        )
        bal1 = result[1]
        assert bal1.balance == Decimal("30")
        assert bal1.has_mixed_currencies is False

        bal2 = result[2]
        # 10000 ARS + 10 USD converted to ARS (10 * 1200 = 12000) = 22000 - 5000 = 17000.
        assert bal2.balance == Decimal("17000")
        assert bal2.has_mixed_currencies is True

    def test_no_rate_map_returns_raw_sum(self):
        # Mixed currencies but no rate_map (rates unavailable). Falls back to raw sum.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"USD": 100.0, "ARS": 1200.0}},
            settlement_sums={1: 0.0},
            rate_map=None,
        )
        bal = result[1]
        # No conversion: 100 + 1200 = 1300 (meaningless but safe fallback).
        assert bal.balance == Decimal("1300")
        assert bal.has_mixed_currencies is True
