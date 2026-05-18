from decimal import Decimal

from app.services.credit_card_service import compute_card_balances

# --- compute_card_balances (per-currency bucket model) ---


class TestComputeCardBalances:
    def test_single_currency_returns_one_bucket(self):
        # Card in USD, all expenses in USD.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"USD": 100.0}},
            settlement_grouped={1: {"USD": 30.0}},
        )
        buckets = result[1]
        assert len(buckets) == 1
        assert buckets[0].currency == "USD"
        assert buckets[0].balance == Decimal("70")

    def test_no_activity_returns_zero_primary_bucket(self):
        # Card with no expenses or settlements yet — bucket exists with 0 balance.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={},
            settlement_grouped={},
        )
        buckets = result[1]
        assert len(buckets) == 1
        assert buckets[0].currency == "USD"
        assert buckets[0].balance == Decimal("0")

    def test_multi_currency_returns_one_bucket_per_currency(self):
        # ARS card with peso and dollar activity — two independent buckets.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "ARS"},
            expense_grouped={1: {"ARS": 50000.0, "USD": 100.0}},
            settlement_grouped={1: {"ARS": 20000.0, "USD": 40.0}},
        )
        buckets = result[1]
        assert len(buckets) == 2
        # Primary (ARS) comes first.
        assert buckets[0].currency == "ARS"
        assert buckets[0].balance == Decimal("30000")
        # Secondary in alphabetical order.
        assert buckets[1].currency == "USD"
        assert buckets[1].balance == Decimal("60")

    def test_buckets_are_not_converted_across_currencies(self):
        # The whole point of Option B: each bucket settles in its own currency.
        # Even with a "rate map" available externally, the function returns raw bucket totals.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"USD": 100.0, "ARS": 1200.0}},
            settlement_grouped={},
        )
        buckets = result[1]
        assert {b.currency: b.balance for b in buckets} == {
            "USD": Decimal("100"),
            "ARS": Decimal("1200"),
        }

    def test_settlement_in_non_primary_currency(self):
        # Settling the USD bucket of an ARS card directly.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "ARS"},
            expense_grouped={1: {"USD": 100.0}},
            settlement_grouped={1: {"USD": 100.0}},
        )
        buckets = result[1]
        # Primary ARS bucket: no activity -> 0.
        ars = next(b for b in buckets if b.currency == "ARS")
        assert ars.balance == Decimal("0")
        # USD bucket: settled to zero.
        usd = next(b for b in buckets if b.currency == "USD")
        assert usd.balance == Decimal("0")

    def test_settlement_exceeds_expenses_yields_negative_bucket(self):
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "ARS"},
            expense_grouped={1: {"ARS": 5000.0}},
            settlement_grouped={1: {"ARS": 8000.0}},
        )
        buckets = result[1]
        assert len(buckets) == 1
        assert buckets[0].currency == "ARS"
        assert buckets[0].balance == Decimal("-3000")

    def test_multiple_cards_each_get_their_own_buckets(self):
        result = compute_card_balances(
            card_ids=[1, 2],
            card_currencies={1: "USD", 2: "ARS"},
            expense_grouped={
                1: {"USD": 50.0},
                2: {"ARS": 10000.0, "USD": 10.0},
            },
            settlement_grouped={
                1: {"USD": 20.0},
                2: {"ARS": 5000.0},
            },
        )
        # Card 1: single USD bucket, 50 - 20 = 30.
        c1 = result[1]
        assert len(c1) == 1
        assert c1[0].currency == "USD"
        assert c1[0].balance == Decimal("30")

        # Card 2: ARS primary + USD secondary.
        c2 = result[2]
        c2_by_cur = {b.currency: b.balance for b in c2}
        assert c2_by_cur == {"ARS": Decimal("5000"), "USD": Decimal("10")}

    def test_primary_always_listed_first(self):
        # Even when the only activity is in a non-primary currency, primary still leads.
        result = compute_card_balances(
            card_ids=[1],
            card_currencies={1: "USD"},
            expense_grouped={1: {"ARS": 1000.0, "EUR": 50.0}},
            settlement_grouped={},
        )
        currencies = [b.currency for b in result[1]]
        assert currencies[0] == "USD"
        # The rest sorted alphabetically.
        assert currencies[1:] == ["ARS", "EUR"]

    def test_empty_card_ids(self):
        assert compute_card_balances([], {}, {}, {}) == {}
