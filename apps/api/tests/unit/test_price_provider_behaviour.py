from decimal import Decimal

import httpx
import pytest

from app.services import price_providers
from app.services.price_providers import PriceProviderUnavailable

# How each provider decides between "I could not answer" and "the answer is nothing" (INFRA-9), plus
# the ticker translation that lets two providers disagree about what a ticker IS.
#
# Every case here is one a provider answers with HTTP 200, which is what makes them worth pinning: a
# non-200 is caught by raise_for_status and needs no test, while these look like success to the
# transport and are only distinguishable by reading the body.


# A fake httpx.AsyncClient yielding a canned status + JSON, or raising.
def _fake_client(*, json_body=None, status: int = 200, error: Exception | None = None, captured: list | None = None):
    class _Response:
        status_code = status

        def raise_for_status(self):
            if status >= 400:
                raise httpx.HTTPStatusError(f"{status}", request=None, response=None)

        def json(self):
            return json_body

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None, headers=None):
            if captured is not None:
                captured.append((url, params))
            if error is not None:
                raise error
            return _Response()

    return _Client


class TestCoinGeckoReportsARateLimitItServesWithHTTP200:
    @pytest.mark.asyncio
    async def test_a_429_carried_in_the_BODY_is_a_provider_failure(self, monkeypatch):
        # Reproduced live before it was written: CoinGecko answers a throttled request with HTTP 200 and
        # the error inside `status`, so raise_for_status never fires and `prices` is simply absent. Read
        # as an empty list — which is exactly the shape of a coin with no history — a rate-limited
        # refresh was indistinguishable from a quiet market, and a chain built on that would never fall
        # back. Three calls in a row were enough to trigger it.
        body = {"status": {"error_code": 429, "error_message": "You've exceeded the Rate Limit"}}
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(json_body=body))

        with pytest.raises(PriceProviderUnavailable, match="rate-limited"):
            await price_providers.fetch_coingecko("bitcoin")

    @pytest.mark.asyncio
    async def test_a_genuinely_empty_series_is_an_ANSWER_not_a_failure(self, monkeypatch):
        # The other side of the same branch: no `status` error, no prices. The provider worked and the
        # coin has no data — the chain must stop here rather than ask the next provider the same thing.
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(json_body={"prices": []}))

        assert await price_providers.fetch_coingecko("bitcoin") == []

    @pytest.mark.asyncio
    async def test_a_transport_error_is_a_provider_failure(self, monkeypatch):
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(error=httpx.ConnectError("simulated outage")))

        with pytest.raises(PriceProviderUnavailable):
            await price_providers.fetch_coingecko("bitcoin")


class TestTheTwoCryptoProvidersDisagreeAboutWhatATickerIs:
    # CoinGecko addresses a coin by id ("bitcoin") and 404s on a symbol; Coinbase wants the symbol
    # ("BTC"). Nothing validates the ticker on entry, so both spellings exist in real data — a holding
    # stored as "BTC" fetched nothing at all, silently, for as long as it had been there.

    def test_a_symbol_becomes_a_coingecko_id(self):
        assert price_providers.to_coingecko_id("BTC") == "bitcoin"
        assert price_providers.to_coingecko_id("eth") == "ethereum"

    def test_a_coin_id_is_left_alone(self):
        assert price_providers.to_coingecko_id("bitcoin") == "bitcoin"

    def test_a_coin_id_becomes_a_symbol(self):
        assert price_providers.to_crypto_symbol("bitcoin") == "BTC"
        assert price_providers.to_crypto_symbol("BTC") == "BTC"

    def test_an_unlisted_ticker_passes_through_both_ways(self):
        # The table covers the coins people actually hold, not all ten thousand. An unknown ticker must
        # still reach whichever provider already spells it that way rather than being mangled.
        assert price_providers.to_coingecko_id("SOMECOIN") == "SOMECOIN"
        assert price_providers.to_crypto_symbol("somecoin") == "SOMECOIN"

    def test_the_two_directions_agree_for_every_listed_coin(self):
        # Stated as a relationship over the whole table rather than per coin, so an entry added later is
        # covered by the same assertion instead of needing its own.
        for symbol, coin_id in price_providers._COINGECKO_IDS_BY_SYMBOL.items():
            assert price_providers.to_coingecko_id(symbol) == coin_id
            assert price_providers.to_crypto_symbol(coin_id) == symbol


class TestCoinbaseSeparatesAnUnlistedAssetFromAnOutage:
    @pytest.mark.asyncio
    async def test_a_404_is_an_empty_answer(self, monkeypatch):
        # Coinbase lists a few hundred assets against CoinGecko's thousands, so "not listed here" is a
        # normal answer for a long-tail coin — not a reason to report the provider down.
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(status=404))

        assert await price_providers.fetch_coinbase("SOMECOIN") == []

    @pytest.mark.asyncio
    async def test_a_price_is_returned_for_either_ticker_spelling(self, monkeypatch):
        captured: list = []
        body = {"data": {"amount": "75817.05", "base": "BTC", "currency": "USD"}}
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(json_body=body, captured=captured))

        rows = await price_providers.fetch_coinbase("bitcoin")

        assert [row[1] for row in rows] == [Decimal("75817.05")]
        assert [row[2] for row in rows] == ["USD"]
        assert "BTC-USD" in captured[0][0], "the coin id must be translated to the symbol Coinbase wants"

    @pytest.mark.asyncio
    async def test_a_transport_error_is_a_provider_failure(self, monkeypatch):
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(error=httpx.ConnectError("down")))

        with pytest.raises(PriceProviderUnavailable):
            await price_providers.fetch_coinbase("BTC")


class TestFinnhubSeparatesAnUnknownSymbolFromAnOutage:
    @pytest.mark.asyncio
    async def test_a_zeroed_quote_is_an_empty_answer(self, monkeypatch):
        # Finnhub answers an unknown symbol with HTTP 200 and every field zero rather than a 404, so a
        # zero current price means "no such symbol" — an answer, not a failure.
        from app.config import settings

        monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(json_body={"c": 0, "h": 0, "l": 0}))

        assert await price_providers.fetch_finnhub("NOSUCH") == []

    @pytest.mark.asyncio
    async def test_no_key_configured_is_a_provider_failure_not_an_empty_answer(self, monkeypatch):
        # Belt and braces with the chain's is_configured skip: if Finnhub is ever reached without a key,
        # it must not report "this ticker has no price" and stop the chain on a configuration problem.
        from app.config import settings

        monkeypatch.setattr(settings, "finnhub_api_key", None)

        with pytest.raises(PriceProviderUnavailable, match="no API key"):
            await price_providers.fetch_finnhub("AAPL")

    def test_is_configured_follows_the_setting(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "finnhub_api_key", None)
        assert price_providers.finnhub_is_configured() is False
        monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
        assert price_providers.finnhub_is_configured() is True


class TestData912SpeaksBYMASymbols:
    @pytest.mark.asyncio
    async def test_the_BA_suffix_renly_stores_is_stripped_for_the_lookup(self, monkeypatch):
        # Renly stores a BYMA listing the way Yahoo spells it (AAPL.BA) because yfinance is the primary;
        # data912 uses the bare symbol. Without the strip the fallback finds nothing for every single
        # CEDEAR — which would look exactly like data912 not carrying them.
        monkeypatch.setattr(price_providers, "_data912_prices", {"AAPL": Decimal("26600")})

        rows = await price_providers.fetch_data912("AAPL.BA")

        assert [(row[1], row[2]) for row in rows] == [(Decimal("26600"), "ARS")]

    @pytest.mark.asyncio
    async def test_a_symbol_the_board_does_not_carry_is_an_empty_answer(self, monkeypatch):
        monkeypatch.setattr(price_providers, "_data912_prices", {"AAPL": Decimal("26600")})

        assert await price_providers.fetch_data912("NOSUCH") == []

    @pytest.mark.asyncio
    async def test_a_failed_board_download_is_a_provider_failure(self, monkeypatch):
        monkeypatch.setattr(price_providers, "_data912_prices", None)
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(error=httpx.ConnectError("down")))

        with pytest.raises(PriceProviderUnavailable):
            await price_providers.fetch_data912("AAPL.BA")

    @pytest.mark.asyncio
    async def test_clearing_the_cache_forces_the_next_cycle_to_re_download(self, monkeypatch):
        monkeypatch.setattr(price_providers, "_data912_prices", {"AAPL": Decimal("1")})
        price_providers.clear_data912_cache()
        assert price_providers._data912_prices is None
