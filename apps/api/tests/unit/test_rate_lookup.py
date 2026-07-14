from datetime import date
from decimal import Decimal

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.utils.metrics import RateLookup, convert_value

# --- Helpers ---


def _rate(pair: ExchangeRatePair, rate_date: date, value: str) -> ExchangeRate:
    return ExchangeRate(date=rate_date, pair=pair, rate=Decimal(value), source="test")


# --- RateLookup ---


class TestRateLookupGetRateMapAt:
    def test_returns_none_when_no_rates_stored(self):
        lookup = RateLookup(dollar_preference="mep", rates_by_pair={})
        assert lookup.get_rate_map_at(date(2026, 1, 1)) is None

    def test_uses_latest_rate_at_or_before_date(self):
        # ARS rate moves from 1000 (Jan 1) to 1100 (Jan 15) to 1200 (Feb 1).
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 1), "1000"),
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 15), "1100"),
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 2, 1), "1200"),
            ],
        }
        lookup = RateLookup(dollar_preference="mep", rates_by_pair=rates)

        # On the rate's exact date: that rate.
        assert lookup.get_rate_map_at(date(2026, 1, 1))["ARS"] == Decimal("1000")
        # Between two rates: the earlier one.
        assert lookup.get_rate_map_at(date(2026, 1, 10))["ARS"] == Decimal("1000")
        # On / after a later rate: the later one.
        assert lookup.get_rate_map_at(date(2026, 1, 15))["ARS"] == Decimal("1100")
        assert lookup.get_rate_map_at(date(2026, 1, 31))["ARS"] == Decimal("1100")
        assert lookup.get_rate_map_at(date(2026, 2, 1))["ARS"] == Decimal("1200")
        # After every stored rate: still uses the latest stored one.
        assert lookup.get_rate_map_at(date(2030, 1, 1))["ARS"] == Decimal("1200")

    def test_pre_history_fallback_uses_earliest_rate(self):
        # No rate predates Jan 15, 2026, but the lookup falls back to the earliest available
        # so the page renders even for ancient dates.
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 15), "1100"),
            ],
        }
        lookup = RateLookup(dollar_preference="mep", rates_by_pair=rates)
        assert lookup.get_rate_map_at(date(2020, 1, 1))["ARS"] == Decimal("1100")

    def test_respects_dollar_preference(self):
        rates = {
            ExchangeRatePair.USD_ARS_OFICIAL: [_rate(ExchangeRatePair.USD_ARS_OFICIAL, date(2026, 1, 1), "900")],
            ExchangeRatePair.USD_ARS_MEP: [_rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 1), "1000")],
            ExchangeRatePair.USD_ARS_BLUE: [_rate(ExchangeRatePair.USD_ARS_BLUE, date(2026, 1, 1), "1100")],
        }
        d = date(2026, 1, 1)
        assert RateLookup("oficial", rates).get_rate_map_at(d)["ARS"] == Decimal("900")
        assert RateLookup("mep", rates).get_rate_map_at(d)["ARS"] == Decimal("1000")
        assert RateLookup("blue", rates).get_rate_map_at(d)["ARS"] == Decimal("1100")

    def test_falls_back_to_mep_when_preferred_pair_missing(self):
        # Only MEP is stored; even with oficial preference we fall back to MEP rather than miss ARS.
        rates = {ExchangeRatePair.USD_ARS_MEP: [_rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 1), "1000")]}
        lookup = RateLookup("oficial", rates)
        assert lookup.get_rate_map_at(date(2026, 1, 1))["ARS"] == Decimal("1000")

    def test_non_ars_pairs(self):
        rates = {
            ExchangeRatePair.USD_BRL: [_rate(ExchangeRatePair.USD_BRL, date(2026, 1, 1), "5")],
            ExchangeRatePair.USD_EUR: [_rate(ExchangeRatePair.USD_EUR, date(2026, 1, 1), "0.9")],
            ExchangeRatePair.USD_GBP: [_rate(ExchangeRatePair.USD_GBP, date(2026, 1, 1), "0.8")],
        }
        lookup = RateLookup("mep", rates)
        rate_map = lookup.get_rate_map_at(date(2026, 1, 1))
        assert rate_map["USD"] == Decimal("1")
        assert rate_map["BRL"] == Decimal("5")
        assert rate_map["EUR"] == Decimal("0.9")
        assert rate_map["GBP"] == Decimal("0.8")
        # ARS missing entirely is OK — the page falls back to original currency.
        assert "ARS" not in rate_map

    def test_caches_per_date_lookups(self):
        # Same date returns the same dict (memoised). Different dates may return different dicts.
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 1), "1000"),
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 2, 1), "1200"),
            ],
        }
        lookup = RateLookup("mep", rates)
        m1 = lookup.get_rate_map_at(date(2026, 1, 15))
        m2 = lookup.get_rate_map_at(date(2026, 1, 15))
        m3 = lookup.get_rate_map_at(date(2026, 2, 15))
        assert m1 is m2  # same date hits the cache.
        assert m1 is not m3  # different dates build different maps.


# --- convert_value through historical rates ---


class TestConvertValueHistorical:
    def test_jan_value_uses_jan_rate(self):
        # 100 USD in Jan (rate 1000 ARS/USD) -> 100,000 ARS. Same 100 USD in Feb (rate 1200) -> 120,000 ARS.
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 1), "1000"),
                _rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 2, 1), "1200"),
            ],
        }
        lookup = RateLookup("mep", rates)

        jan_map = lookup.get_rate_map_at(date(2026, 1, 15))
        feb_map = lookup.get_rate_map_at(date(2026, 2, 15))
        assert convert_value(Decimal("100"), "USD", "ARS", jan_map) == Decimal("100000")
        assert convert_value(Decimal("100"), "USD", "ARS", feb_map) == Decimal("120000")

    def test_pivot_via_usd_uses_both_pair_rates_at_same_date(self):
        # BRL -> EUR pivots through USD. Both pair quotes are sampled at the requested date.
        rates = {
            ExchangeRatePair.USD_BRL: [_rate(ExchangeRatePair.USD_BRL, date(2026, 1, 1), "5")],
            ExchangeRatePair.USD_EUR: [_rate(ExchangeRatePair.USD_EUR, date(2026, 1, 1), "1")],
        }
        lookup = RateLookup("mep", rates)
        rate_map = lookup.get_rate_map_at(date(2026, 1, 1))
        # 50 BRL = 10 USD = 10 EUR.
        assert convert_value(Decimal("50"), "BRL", "EUR", rate_map) == Decimal("10")

    def test_non_terminating_division_is_quantized_to_two_decimals(self):
        # Regression: raw `value / from_rate * to_rate` runs under Python's default 28-digit
        # Decimal context, so 1/3*5 = Decimal('1.666666666666666666666666667') (28 digits).
        # Every response schema field that holds a converted amount declares max_digits=18,
        # so the un-quantized result overflowed the Pydantic validator and surfaced as 500s
        # on `GET /payments-calendar?currency=BRL` (and every other display-currency switch
        # whose rate combo didn't terminate cleanly). The fix quantizes to 2 decimal places
        # inside `convert_value` — verified here by counting digits on the returned Decimal.
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [_rate(ExchangeRatePair.USD_ARS_MEP, date(2026, 1, 1), "3")],
            ExchangeRatePair.USD_BRL: [_rate(ExchangeRatePair.USD_BRL, date(2026, 1, 1), "5")],
        }
        lookup = RateLookup("mep", rates)
        rate_map = lookup.get_rate_map_at(date(2026, 1, 1))
        # 1 ARS / 3 (ARS per USD) * 5 (BRL per USD) = 1.6666... -> banker's-rounded to 1.67.
        result = convert_value(Decimal("1"), "ARS", "BRL", rate_map)
        assert result == Decimal("1.67")
        # Total digit count must fit the 18-digit Pydantic ceiling; quantize forces 2 places.
        _sign, digits, exponent = result.as_tuple()
        assert len(digits) <= 18
        assert exponent == -2

    def test_identity_conversion_preserves_input_decimal(self):
        # When from == to, convert_value short-circuits and returns the input unchanged.
        # Confirm the quantize step does NOT apply on the identity path (the caller's
        # precision is left as-is, matching prior behaviour).
        rates: dict[ExchangeRatePair, list] = {}
        lookup = RateLookup("mep", rates)
        rate_map = lookup.get_rate_map_at(date(2026, 1, 1)) or {}
        unchanged = convert_value(Decimal("1.234"), "USD", "USD", rate_map)
        assert unchanged == Decimal("1.234")

    def test_missing_pair_returns_none(self):
        # When either side is missing from the rate map, convert_value fails loud and returns
        # None so callers skip the row instead of summing an unconverted value.
        rates = {
            ExchangeRatePair.USD_BRL: [_rate(ExchangeRatePair.USD_BRL, date(2026, 1, 1), "5")],
        }
        lookup = RateLookup("mep", rates)
        rate_map = lookup.get_rate_map_at(date(2026, 1, 1))
        # ARS rate is missing -> fail loud, return None.
        assert convert_value(Decimal("1.234"), "ARS", "BRL", rate_map) is None
