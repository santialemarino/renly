from datetime import date
from decimal import Decimal

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.services.finance_metrics_service import _sum_converted
from app.utils.metrics import RateLookup


# Real RateLookup storing only the MEP pair — USD and ARS convert, everything else is missing.
def _lookup() -> RateLookup:
    rates = {
        ExchangeRatePair.USD_ARS_MEP: [
            ExchangeRate(date=date(2026, 1, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1000"), source="test"),
        ],
    }
    return RateLookup(dollar_preference="mep", rates_by_pair=rates)


class TestSumConvertedSkips:
    def test_missing_rate_bucket_excluded_and_reported(self):
        total, skipped = _sum_converted({"USD": 100.0, "CLP": 5000.0}, "USD", _lookup(), date(2026, 1, 15))
        assert total == Decimal("100")
        assert skipped == {"CLP"}

    def test_no_target_currency_sums_raw(self):
        total, skipped = _sum_converted({"USD": 100.0}, None, None, date(2026, 1, 15))
        assert total == Decimal("100")
        assert skipped == set()
