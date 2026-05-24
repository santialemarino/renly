from datetime import date as date_type
from decimal import Decimal

from app.services.dashboard_service import compute_monthly_card_balances

# Rate map: 1 USD = 1200 ARS.
RATE_MAP = {
    "USD": Decimal("1"),
    "ARS": Decimal("1200"),
}


# Stub RateLookup that returns the same rate map for any date — keeps the existing tests focused
# on the per-currency aggregation logic rather than the date-aware lookup behaviour (which has
# its own coverage in test_metrics_helpers / test_rate_lookup).
class _FixedLookup:
    def __init__(self, rate_map: dict[str, Decimal] | None) -> None:
        self._rate_map = rate_map

    def get_rate_map_at(self, _as_of_date: date_type) -> dict[str, Decimal] | None:
        return self._rate_map


FIXED_LOOKUP = _FixedLookup(RATE_MAP)


# --- compute_monthly_card_balances (5-tuple settlement / expense shape) ---


class TestComputeMonthlyCardBalances:
    def test_single_card_single_currency(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 2, "USD", 50.0),
        ]
        settlements = [
            (1, 2026, 2, "USD", 80.0),
        ]
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # Jan: 100 - 0 = 100. Feb: 100 + 50 - 80 = 70.
        assert result[(2026, 1)] == Decimal("100")
        assert result[(2026, 2)] == Decimal("70")

    def test_multi_card_multi_currency_converts_each_bucket(self):
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
            lookup=FIXED_LOOKUP,
        )
        # 100 USD + (1200 ARS -> 1 USD) = 101 USD.
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
            lookup=FIXED_LOOKUP,
        )
        # Jan: 100. Mar: 100 + 50 = 150. Feb has no data, not in result.
        assert result[(2026, 1)] == Decimal("100")
        assert (2026, 2) not in result
        assert result[(2026, 3)] == Decimal("150")

    def test_settlement_exceeds_expenses(self):
        expenses = [(1, 2026, 1, "USD", 50.0)]
        settlements = [(1, 2026, 1, "USD", 100.0)]
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # Overpayment: 50 - 100 = -50.
        assert result[(2026, 1)] == Decimal("-50")

    def test_empty_inputs(self):
        result = compute_monthly_card_balances(
            [],
            [],
            card_currencies={},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        assert result == {}

    def test_no_target_currency_passes_values_through(self):
        # When no target currency is set, every bucket's value is summed raw.
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
            lookup=None,
        )
        # No conversion: 100 + 500 = 600.
        assert result[(2026, 1)] == Decimal("600")

    def test_foreign_bucket_settled_in_its_own_currency(self):
        # ARS card with USD bucket activity — both expense and settlement live in USD,
        # so the USD bucket cancels cleanly without going through card currency.
        expenses = [(1, 2026, 1, "USD", 50.0)]
        settlements = [(1, 2026, 1, "USD", 50.0)]
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "ARS"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        assert result[(2026, 1)] == Decimal("0")

    def test_each_bucket_converts_from_its_own_currency(self):
        # ARS-currency settlement on a USD card converts directly from ARS, not via card currency.
        expenses = [(1, 2026, 1, "USD", 100.0)]
        settlements = [(1, 2026, 1, "ARS", 1200.0)]  # 1200 ARS = 1 USD.
        result = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # 100 USD expense - 1 USD settlement (from 1200 ARS) = 99 USD.
        assert result[(2026, 1)] == Decimal("99")
