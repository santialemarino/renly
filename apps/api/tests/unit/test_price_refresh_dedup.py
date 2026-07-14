import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.models.investment import Investment, InvestmentCategory
from app.services import asset_price_service
from app.services.price_providers import PriceProviderInfo

# Unit coverage for the price-refresh dedup + bounded concurrency (P08 perf): N holders of the same
# ticker cost one provider fetch, and the parallel fan-out never exceeds the semaphore bound. The
# provider fetch + bulk_upsert are faked (no network, no DB).


class _FetchRecorder:
    def __init__(self):
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def __call__(self, ticker, start_date, end_date):
        self.calls.append(ticker)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        return [(date(2026, 7, 1), Decimal("10"), "USD")]


class FakeSession:
    async def commit(self):
        return None


class TestPriceRefreshDedup:
    @pytest.mark.asyncio
    async def test_duplicate_tickers_fetch_once_and_concurrency_is_bounded(self, monkeypatch):
        recorder = _FetchRecorder()
        provider = PriceProviderInfo(source="test", fetch=recorder, supports_history=False)
        monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.cedears: provider})

        stored = {"n": 0}

        async def fake_bulk_upsert(session, prices):
            stored["n"] += len(prices)
            return len(prices)

        monkeypatch.setattr(asset_price_service.asset_price_repository, "bulk_upsert", fake_bulk_upsert)

        # 30 investments over 20 unique tickers (AAPL held by 11 investments).
        investments = [
            Investment(id=i, user_id=1, name=f"inv{i}", category=InvestmentCategory.cedears, base_currency="USD", ticker="AAPL") for i in range(11)
        ] + [
            Investment(id=100 + i, user_id=1, name=f"u{i}", category=InvestmentCategory.cedears, base_currency="USD", ticker=f"T{i:02d}")
            for i in range(19)
        ]

        total = await asset_price_service._refresh_prices_for_investments(FakeSession(), investments)

        assert sorted(recorder.calls) == sorted({"AAPL", *[f"T{i:02d}" for i in range(19)]})  # one fetch per unique ticker
        assert recorder.max_active <= asset_price_service.MAX_CONCURRENT_PRICE_FETCHES
        assert total == 20 and stored["n"] == 20
