import pytest

from app.services import exchange_rate_service

# Unit coverage for the process-level TTL cache backing the grouped-rates load (P08 perf): a single
# repo load serves repeated lookups within the TTL; the clock passing the TTL or an explicit
# invalidation forces a reload. The repo load + monotonic clock are faked (no DB).


class TestRatesCache:
    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        exchange_rate_service.invalidate_rates_cache()
        yield
        exchange_rate_service.invalidate_rates_cache()

    # One repo load serves repeated lookups within the TTL.
    @pytest.mark.asyncio
    async def test_serves_cached_copy_within_ttl(self, monkeypatch):
        calls = {"n": 0}

        async def fake_load(session):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(exchange_rate_service.exchange_rate_repository, "get_all_grouped_by_pair", fake_load)
        clock = {"now": 1000.0}
        monkeypatch.setattr(exchange_rate_service.time, "monotonic", lambda: clock["now"])

        await exchange_rate_service.get_rates_grouped_by_pair_cached(None)
        clock["now"] += exchange_rate_service.RATES_CACHE_TTL_SECONDS - 1
        await exchange_rate_service.get_rates_grouped_by_pair_cached(None)
        assert calls["n"] == 1

    # The clock passing the TTL forces a reload.
    @pytest.mark.asyncio
    async def test_reloads_after_ttl(self, monkeypatch):
        calls = {"n": 0}

        async def fake_load(session):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(exchange_rate_service.exchange_rate_repository, "get_all_grouped_by_pair", fake_load)
        clock = {"now": 1000.0}
        monkeypatch.setattr(exchange_rate_service.time, "monotonic", lambda: clock["now"])

        await exchange_rate_service.get_rates_grouped_by_pair_cached(None)
        clock["now"] += exchange_rate_service.RATES_CACHE_TTL_SECONDS + 1
        await exchange_rate_service.get_rates_grouped_by_pair_cached(None)
        assert calls["n"] == 2

    # Explicit invalidation (the scheduler hook) forces a reload before the TTL.
    @pytest.mark.asyncio
    async def test_invalidate_forces_reload(self, monkeypatch):
        calls = {"n": 0}

        async def fake_load(session):
            calls["n"] += 1
            return {}

        monkeypatch.setattr(exchange_rate_service.exchange_rate_repository, "get_all_grouped_by_pair", fake_load)
        clock = {"now": 1000.0}
        monkeypatch.setattr(exchange_rate_service.time, "monotonic", lambda: clock["now"])

        await exchange_rate_service.get_rates_grouped_by_pair_cached(None)
        exchange_rate_service.invalidate_rates_cache()
        await exchange_rate_service.get_rates_grouped_by_pair_cached(None)
        assert calls["n"] == 2
