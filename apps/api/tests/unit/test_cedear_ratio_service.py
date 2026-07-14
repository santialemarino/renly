from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.services import cedear_ratio_service
from app.services.price_providers import RatioFetchResult

# Coverage for the CEDEAR ratio store: fetch_and_store_ratios dedupes the picked source by ticker
# (last entry wins, matching the retired per-row upsert order) and persists it via a single
# bulk_upsert inside one committed transaction.


class TestFetchAndStoreDedupe:
    @pytest.mark.asyncio
    async def test_repeated_ticker_dedupes_last_wins_single_bulk_upsert(self, monkeypatch):
        # Comafi wins (BYMA returns nothing); its list repeats AAPL — the later ratio must survive.
        comafi = RatioFetchResult(
            [("AAPL", "AAPL", Decimal("10")), ("MSFT", "MSFT", Decimal("5")), ("AAPL", "AAPL", Decimal("20"))],
            date(2026, 1, 2),
        )
        monkeypatch.setattr(cedear_ratio_service.price_providers, "fetch_comafi_ratios", AsyncMock(return_value=comafi))
        monkeypatch.setattr(
            cedear_ratio_service.price_providers,
            "fetch_byma_ratios",
            AsyncMock(return_value=RatioFetchResult([], None)),
        )
        bulk_upsert = AsyncMock(return_value=2)
        monkeypatch.setattr(cedear_ratio_service.cedear_ratio_repository, "bulk_upsert", bulk_upsert)
        session = AsyncMock()

        stored = await cedear_ratio_service.fetch_and_store_ratios(session)

        # One bulk upsert, one commit — no per-row loop.
        bulk_upsert.assert_awaited_once()
        session.commit.assert_awaited_once()

        ratios = bulk_upsert.await_args.args[1]
        tickers = [r.ticker for r in ratios]
        assert len(tickers) == len(set(tickers))  # unique (ticker, effective_date) rows
        assert sorted(tickers) == ["AAPL", "MSFT"]
        aapl = next(r for r in ratios if r.ticker == "AAPL")
        assert aapl.ratio == Decimal("20")  # last entry wins
        assert stored == 2  # bulk_upsert's deduped count is returned to the caller
