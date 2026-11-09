import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.models.exchange_rate import ExchangeRatePair
from app.services import exchange_rate_providers as providers
from app.services.exchange_rate_providers import ExchangeRateHistoryUnavailable, ExchangeRateQuote

# The exchange-rate providers' parsing and, above all, the DATE each quote is stored under. The fixtures
# are trimmed copies of real responses recorded on Sunday 2026-11-08, so each case reads what the source
# actually sends: DolarApi's oficial quote last updated on the Thursday, Frankfurter's latest dated the
# Friday, and ArgentinaDatos repeating the last quote on weekends and listing a day that has not
# happened yet. No test here reaches the network: the HTTP client is a fake returning a real httpx.Response.

_FIXTURES = Path(__file__).parent / "fixtures" / "exchange_rates"
# The day the fixtures were recorded, used as the server's date.
_RECORDED_ON = date(2026, 11, 8)

_OFICIAL = ExchangeRatePair.USD_ARS_OFICIAL
_BLUE = ExchangeRatePair.USD_ARS_BLUE
_MEP = ExchangeRatePair.USD_ARS_MEP


# Reads one recorded response.
def _fixture(name: str):
    return json.loads((_FIXTURES / name).read_text())


# A fake httpx.AsyncClient answering each URL from `bodies` (a URL missing from it answers 404), and
# recording the URLs asked for. `error` makes every request raise it instead.
def _fake_client(bodies: dict[str, object], requested: list[str], error: Exception | None = None):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None, headers=None):
            requested.append(url)
            if error is not None:
                raise error
            request = httpx.Request("GET", url)
            if url not in bodies:
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request, json=bodies[url])

    return _Client


class TestDolarApiDatesEachQuoteByItsOwnTimestamp:
    # The bug this replaces: every quote was stored under the server's date. On the recorded Sunday the
    # oficial quote had last been updated on Thursday 2026-11-05 (18:55 UTC), so the old fetcher filed
    # Thursday's quote as Sunday's.
    def test_each_pair_takes_the_date_of_its_fechaActualizacion(self):
        quotes = providers.parse_dolarapi(_fixture("dolarapi_dolares.json"), _RECORDED_ON)

        assert {q.pair: q.quote_date for q in quotes} == {
            _OFICIAL: date(2026, 11, 5),
            _BLUE: date(2026, 11, 8),
            _MEP: date(2026, 11, 8),
        }

    # The stored figure is the midpoint of buy and sell, as before; the other casas are not stored.
    def test_stores_the_buy_sell_midpoint_of_the_three_pairs_only(self):
        quotes = providers.parse_dolarapi(_fixture("dolarapi_dolares.json"), _RECORDED_ON)

        assert {q.pair: q.rate for q in quotes} == {
            _OFICIAL: Decimal("1545"),  # (1520 + 1570) / 2
            _BLUE: Decimal("1545"),  # (1535 + 1555) / 2
            _MEP: Decimal("1574.05"),  # (1560.2 + 1587.9) / 2
        }

    # The date is Argentina's (UTC-3): a quote stamped 01:30 UTC was quoted the evening before.
    def test_the_date_is_the_argentine_calendar_day(self):
        body = [{"casa": "blue", "compra": 10, "venta": 20, "fechaActualizacion": "2026-11-06T01:30:00.000Z"}]

        assert providers.parse_dolarapi(body, _RECORDED_ON) == [ExchangeRateQuote(_BLUE, Decimal("15"), date(2026, 11, 5))]

    # Without a readable timestamp the server's date is the only date left.
    @pytest.mark.parametrize("stamp", [None, "not a date"])
    def test_falls_back_to_the_server_date_without_a_timestamp(self, stamp):
        body = [{"casa": "oficial", "compra": 10, "venta": 20, "fechaActualizacion": stamp}]

        assert providers.parse_dolarapi(body, _RECORDED_ON)[0].quote_date == _RECORDED_ON

    @pytest.mark.asyncio
    async def test_the_fetch_returns_the_dated_quotes(self, monkeypatch):
        requested: list[str] = []
        url = "https://dolarapi.com/v1/dolares"
        monkeypatch.setattr(providers.httpx, "AsyncClient", _fake_client({url: _fixture("dolarapi_dolares.json")}, requested))

        quotes = await providers.fetch_dolarapi()

        assert requested == [url]
        assert {q.pair: q.quote_date for q in quotes}[_OFICIAL] == date(2026, 11, 5)


class TestFrankfurterLatestIsDatedByTheECBBusinessDay:
    # Read on a Sunday, /latest returns Friday's rates with `"date": "2026-11-06"`.
    def test_takes_the_body_date_not_the_server_date(self):
        quotes = providers.parse_frankfurter_latest(_fixture("frankfurter_latest.json"), _RECORDED_ON)

        assert quotes == [
            ExchangeRateQuote(ExchangeRatePair.USD_BRL, Decimal("5.5037"), date(2026, 11, 6)),
            ExchangeRateQuote(ExchangeRatePair.USD_EUR, Decimal("0.89566"), date(2026, 11, 6)),
            ExchangeRateQuote(ExchangeRatePair.USD_GBP, Decimal("0.74711"), date(2026, 11, 6)),
        ]

    def test_falls_back_to_the_server_date_without_one(self):
        quotes = providers.parse_frankfurter_latest({"rates": {"EUR": 0.9}}, _RECORDED_ON)

        assert quotes == [ExchangeRateQuote(ExchangeRatePair.USD_EUR, Decimal("0.9"), _RECORDED_ON)]


class TestFrankfurterRange:
    # The recorded range was asked for 2026-09-20..2026-09-30 (from a Sunday): the API answers with the
    # Friday before it too, 2026-09-18, which lies outside the range asked for and is dropped.
    def test_keeps_each_business_day_inside_the_range_only(self):
        quotes = providers.parse_frankfurter_range(_fixture("frankfurter_range.json"), date(2026, 9, 20), date(2026, 9, 30))

        dates = sorted({q.quote_date for q in quotes})
        assert dates[0] == date(2026, 9, 21)
        assert date(2026, 9, 18) not in dates
        assert len(dates) == 8 and len(quotes) == 24
        assert ExchangeRateQuote(ExchangeRatePair.USD_EUR, Decimal("0.87635"), date(2026, 9, 23)) in quotes

    @pytest.mark.asyncio
    async def test_the_fetch_asks_for_the_range_and_only_the_pairs_wanted(self, monkeypatch):
        requested: list[str] = []
        url = "https://api.frankfurter.dev/v1/2026-09-20..2026-09-30?base=USD&symbols=EUR"
        monkeypatch.setattr(providers.httpx, "AsyncClient", _fake_client({url: _fixture("frankfurter_range.json")}, requested))

        quotes = await providers.fetch_frankfurter_history(date(2026, 9, 20), date(2026, 9, 30), (ExchangeRatePair.USD_EUR,))

        assert requested == [url]
        # The fake answers with all three symbols; the parser keeps what the body carries.
        assert {q.pair for q in quotes} == {ExchangeRatePair.USD_BRL, ExchangeRatePair.USD_EUR, ExchangeRatePair.USD_GBP}

    @pytest.mark.asyncio
    async def test_a_failed_request_raises_rather_than_reading_as_no_quotes(self, monkeypatch):
        monkeypatch.setattr(providers.httpx, "AsyncClient", _fake_client({}, [], error=httpx.ConnectError("down")))

        with pytest.raises(ExchangeRateHistoryUnavailable):
            await providers.fetch_frankfurter_history(date(2026, 9, 20), date(2026, 9, 30), (ExchangeRatePair.USD_EUR,))


class TestArgentinaDatosSeries:
    # MEP: Friday 10-30 is 1563.3; Saturday 10-31 is a DIFFERENT, later reading (1570.2) and is kept;
    # Sunday 11-01 repeats Saturday and is dropped; Monday 11-02 repeats it too but is a weekday and kept.
    def test_drops_only_weekend_repeats_of_the_day_before(self):
        quotes = providers.parse_argentinadatos(_MEP, _fixture("argentinadatos_bolsa.json"), date(2026, 10, 30), date(2026, 11, 2))

        assert quotes == [
            ExchangeRateQuote(_MEP, Decimal("1563.3"), date(2026, 10, 30)),
            ExchangeRateQuote(_MEP, Decimal("1570.2"), date(2026, 10, 31)),
            ExchangeRateQuote(_MEP, Decimal("1570.2"), date(2026, 11, 2)),
        ]

    # The recorded series already lists Monday 2026-11-09 on the Sunday it was read. The range end bounds it.
    def test_never_returns_a_day_after_the_range_end(self):
        quotes = providers.parse_argentinadatos(_OFICIAL, _fixture("argentinadatos_oficial.json"), date(2026, 11, 1), _RECORDED_ON)

        assert max(q.quote_date for q in quotes) <= _RECORDED_ON
        # Oficial did not move over the weekend: no Saturday or Sunday row at all.
        assert all(q.quote_date.weekday() < 5 for q in quotes)

    @pytest.mark.asyncio
    async def test_the_fetch_reads_one_series_per_pair_wanted(self, monkeypatch):
        requested: list[str] = []
        base = "https://api.argentinadatos.com/v1/cotizaciones/dolares"
        bodies = {f"{base}/{casa}": _fixture(f"argentinadatos_{casa}.json") for casa in ("oficial", "blue", "bolsa")}
        monkeypatch.setattr(providers.httpx, "AsyncClient", _fake_client(bodies, requested))

        quotes = await providers.fetch_argentinadatos_history(date(2026, 11, 2), date(2026, 11, 6), (_BLUE, _MEP))

        assert sorted(requested) == [f"{base}/blue", f"{base}/bolsa"]
        assert {q.pair for q in quotes} == {_BLUE, _MEP}
        assert {q.quote_date for q in quotes} == {date(2026, 11, d) for d in range(2, 7)}

    @pytest.mark.asyncio
    async def test_a_failed_series_raises(self, monkeypatch):
        monkeypatch.setattr(providers.httpx, "AsyncClient", _fake_client({}, []))

        with pytest.raises(ExchangeRateHistoryUnavailable):
            await providers.fetch_argentinadatos_history(date(2026, 11, 2), date(2026, 11, 6), (_BLUE,))


class TestHistoryRegistry:
    # Gap filling looks a missing pair up in this registry; a pair no provider covers would stay missing
    # for ever, and a pair two providers cover would be written twice in one run.
    def test_every_pair_has_exactly_one_history_provider(self):
        covered = [pair for provider in providers.EXCHANGE_RATE_HISTORY_PROVIDERS for pair in provider.pairs]

        assert sorted(covered) == sorted(ExchangeRatePair)
