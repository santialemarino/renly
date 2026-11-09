# Exchange rate provider implementations for fetching rates from external APIs.
# Two kinds: LATEST providers return the current quotes (run by the scheduler), HISTORY providers return
# every daily quote in a date range (run to fill missing days and by the one-off backfill command).
# Every quote carries the date the SOURCE gives it, never the server's date: a weekend or stale quote
# is stored under the day it was quoted for.
# Providers are stateless — they fetch and return, the service handles storage.
# To add a new source, create a fetch function and add it to the matching registry below.

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, timezone
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

import httpx

from app.models.exchange_rate import ExchangeRatePair

logger = logging.getLogger(__name__)

# --- Result types ---


# One quote: the pair, the rate (1 USD = rate units), and the date the source quotes it for.
class ExchangeRateQuote(NamedTuple):
    pair: ExchangeRatePair
    rate: Decimal
    quote_date: date_type


ExchangeRateResult = list[ExchangeRateQuote]


# Raised by a HISTORY provider that could not answer (network error, bad status, unreadable body).
# Unlike the latest providers, which log and return [] so one source never blocks the other, a history
# fetch has to tell "the source has no quotes in this range" apart from "the source did not answer".
class ExchangeRateHistoryUnavailable(Exception):
    pass


# --- Provider metadata ---


# Describes a latest-rate provider: its source name and fetch function.
class ExchangeRateProviderInfo(NamedTuple):
    source: str
    fetch: Callable[..., Awaitable[ExchangeRateResult]]


# Describes a history provider: its source name, the pairs it covers, and fetch(start, end, pairs).
class ExchangeRateHistoryProviderInfo(NamedTuple):
    source: str
    pairs: tuple[ExchangeRatePair, ...]
    fetch: Callable[[date_type, date_type, tuple[ExchangeRatePair, ...]], Awaitable[ExchangeRateResult]]


# Argentina has had a fixed UTC-3 offset (no daylight saving) since 2009. A fixed offset rather than
# a zoneinfo key, so the quote date never depends on the host having tz data installed.
_ARGENTINA_TZ = timezone(timedelta(hours=-3))


# The midpoint of a buy/sell quote, the figure stored for every ARS pair. None when either side is not a
# number (a malformed value skips that quote rather than failing the whole response).
def _midpoint(compra: object, venta: object) -> Decimal | None:
    buy = _decimal(compra)
    sell = _decimal(venta)
    if buy is None or sell is None:
        return None
    return (buy + sell) / 2


# A provider's number as a finite Decimal, or None when it is missing or not a finite number.
def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


# --- DolarApi provider (USD/ARS oficial, MEP, blue; latest) ---

_DOLARAPI_URL = "https://dolarapi.com/v1"

# Maps DolarApi "casa" field to ExchangeRatePair.
_CASA_TO_PAIR = {
    "oficial": ExchangeRatePair.USD_ARS_OFICIAL,
    "blue": ExchangeRatePair.USD_ARS_BLUE,
    "bolsa": ExchangeRatePair.USD_ARS_MEP,
}


# Reads the Argentine calendar date of a DolarApi `fechaActualizacion` timestamp (ISO 8601, UTC "Z").
# Returns None when the field is missing or unreadable.
def _dolarapi_quote_date(raw: object) -> date_type | None:
    if not isinstance(raw, str):
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(_ARGENTINA_TZ).date()


# Parses a DolarApi /dolares body into quotes dated by each item's `fechaActualizacion`. An item
# without a readable timestamp falls back to `fallback_date` (the server's date) — the only date left.
def parse_dolarapi(data: list[dict], fallback_date: date_type) -> ExchangeRateResult:
    results: ExchangeRateResult = []
    for item in data:
        pair = _CASA_TO_PAIR.get(item.get("casa"))
        if pair is None:
            continue
        rate = _midpoint(item.get("compra"), item.get("venta"))
        if rate is None:
            logger.warning("DolarApi quote for %s has no usable compra/venta; skipped.", pair)
            continue
        quote_date = _dolarapi_quote_date(item.get("fechaActualizacion"))
        if quote_date is None:
            logger.warning("DolarApi quote for %s has no readable fechaActualizacion; dating it %s.", pair, fallback_date)
            quote_date = fallback_date
        results.append(ExchangeRateQuote(pair, rate, quote_date))
    return results


# Fetches USD/ARS rates (oficial, blue, MEP) from DolarApi.
# Returns the average of compra/venta for each rate type, dated by the quote's own timestamp.
async def fetch_dolarapi() -> ExchangeRateResult:
    url = f"{_DOLARAPI_URL}/dolares"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        logger.exception("Failed to fetch from DolarApi: %s.", url)
        return []

    results = parse_dolarapi(data, date_type.today())
    if results:
        logger.info("Fetched %d rates from DolarApi.", len(results))
    return results


# --- ArgentinaDatos provider (USD/ARS oficial, MEP, blue; history) ---

_ARGENTINADATOS_URL = "https://api.argentinadatos.com/v1/cotizaciones/dolares"

# Maps ExchangeRatePair to the ArgentinaDatos "casa" path segment (the same names DolarApi uses).
_PAIR_TO_CASA = {pair: casa for casa, pair in _CASA_TO_PAIR.items()}


# Parses one ArgentinaDatos casa series (every calendar day since the series starts, each with
# compra/venta and `fecha`) into quotes dated in [start, end].
# The series repeats the last quote on weekends; a Saturday or Sunday whose quote is IDENTICAL to the
# day before is that repetition and is dropped, because lookups already carry the earlier rate forward
# and a stored copy would invent a quote. A weekend row that differs (the source sometimes records a
# Friday's closing quote on the Saturday) is a real quote and is kept.
def parse_argentinadatos(
    pair: ExchangeRatePair,
    data: list[dict],
    start: date_type,
    end: date_type,
) -> ExchangeRateResult:
    by_date: dict[date_type, Decimal] = {}
    for item in data:
        rate = _midpoint(item.get("compra"), item.get("venta"))
        raw_date = item.get("fecha")
        if rate is None or not isinstance(raw_date, str):
            continue
        try:
            quote_date = date_type.fromisoformat(raw_date)
        except ValueError:
            continue
        by_date[quote_date] = rate

    results: ExchangeRateResult = []
    for quote_date in sorted(by_date):
        if quote_date < start or quote_date > end:
            continue
        rate = by_date[quote_date]
        if quote_date.weekday() >= 5 and by_date.get(quote_date - timedelta(days=1)) == rate:
            continue
        results.append(ExchangeRateQuote(pair, rate, quote_date))
    return results


# Fetches one casa's whole series (the endpoint takes no range). Raises ExchangeRateHistoryUnavailable.
async def _fetch_argentinadatos_casa(client: httpx.AsyncClient, casa: str) -> list[dict]:
    url = f"{_ARGENTINADATOS_URL}/{casa}"
    try:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ExchangeRateHistoryUnavailable(f"ArgentinaDatos {casa}: {type(exc).__name__}") from exc
    if not isinstance(data, list):
        raise ExchangeRateHistoryUnavailable(f"ArgentinaDatos {casa}: unexpected body")
    return data


# Fetches the daily USD/ARS quotes for the given pairs in [start, end] from ArgentinaDatos.
# Oficial and blue start 2011-01-03, MEP ("bolsa") 2018-10-29. One series that fails is logged and its
# pair skipped (it stays missing and is asked for again); raises ExchangeRateHistoryUnavailable only when
# every series failed.
async def fetch_argentinadatos_history(
    start: date_type,
    end: date_type,
    pairs: tuple[ExchangeRatePair, ...],
) -> ExchangeRateResult:
    wanted = [pair for pair in pairs if pair in _PAIR_TO_CASA]
    async with httpx.AsyncClient(timeout=30.0) as client:
        series = await asyncio.gather(
            *[_fetch_argentinadatos_casa(client, _PAIR_TO_CASA[pair]) for pair in wanted],
            return_exceptions=True,
        )
    results: ExchangeRateResult = []
    failures: list[BaseException] = []
    for pair, data in zip(wanted, series):
        if isinstance(data, BaseException):
            logger.warning("ArgentinaDatos: no series for %s (%s); skipped.", pair, data)
            failures.append(data)
            continue
        results.extend(parse_argentinadatos(pair, data, start, end))
    if wanted and len(failures) == len(wanted):
        raise ExchangeRateHistoryUnavailable(f"ArgentinaDatos: every series failed ({failures[0]})")
    return results


# --- Frankfurter provider (USD/BRL, USD/EUR, USD/GBP; latest and history) ---

_FRANKFURTER_URL = "https://api.frankfurter.dev/v1"

# Maps Frankfurter currency symbols to ExchangeRatePair.
_FRANKFURTER_PAIRS = {
    "BRL": ExchangeRatePair.USD_BRL,
    "EUR": ExchangeRatePair.USD_EUR,
    "GBP": ExchangeRatePair.USD_GBP,
}


# Parses one day's Frankfurter `rates` object into quotes dated quote_date.
def _parse_frankfurter_day(rates: dict, quote_date: date_type) -> ExchangeRateResult:
    results: ExchangeRateResult = []
    for symbol, pair in _FRANKFURTER_PAIRS.items():
        value = _decimal(rates.get(symbol))
        if value is None:
            continue
        results.append(ExchangeRateQuote(pair, value, quote_date))
    return results


# Parses a Frankfurter /latest body. The body's `date` is the ECB business day the rates are for
# (Friday's on a weekend); without a readable one, falls back to `fallback_date` (the server's date).
def parse_frankfurter_latest(data: dict, fallback_date: date_type) -> ExchangeRateResult:
    quote_date = fallback_date
    raw_date = data.get("date")
    try:
        quote_date = date_type.fromisoformat(raw_date)
    except (TypeError, ValueError):
        logger.warning("Frankfurter latest has no readable date (%r); dating it %s.", raw_date, fallback_date)
    return _parse_frankfurter_day(data.get("rates", {}), quote_date)


# Parses a Frankfurter range body ({"rates": {"YYYY-MM-DD": {...}}}) into quotes dated in [start, end].
# The API answers a range starting on a closed day with the business day before it, which is dropped.
def parse_frankfurter_range(data: dict, start: date_type, end: date_type) -> ExchangeRateResult:
    results: ExchangeRateResult = []
    for raw_date, rates in sorted(data.get("rates", {}).items()):
        try:
            quote_date = date_type.fromisoformat(raw_date)
        except ValueError:
            continue
        if quote_date < start or quote_date > end:
            continue
        results.extend(_parse_frankfurter_day(rates, quote_date))
    return results


# Fetches USD-based rates (BRL, EUR, GBP) from Frankfurter (ECB data).
# Frankfurter returns rates as "1 USD = X <currency>", matching our storage convention.
async def fetch_frankfurter() -> ExchangeRateResult:
    symbols = ",".join(_FRANKFURTER_PAIRS.keys())
    url = f"{_FRANKFURTER_URL}/latest?base=USD&symbols={symbols}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        logger.exception("Failed to fetch from Frankfurter: %s.", url)
        return []

    results = parse_frankfurter_latest(data, date_type.today())
    if results:
        logger.info("Fetched %d rates from Frankfurter.", len(results))
    return results


# Fetches the ECB business-day rates for the given pairs in [start, end] from Frankfurter in one range
# request. Raises ExchangeRateHistoryUnavailable.
async def fetch_frankfurter_history(
    start: date_type,
    end: date_type,
    pairs: tuple[ExchangeRatePair, ...],
) -> ExchangeRateResult:
    symbols = ",".join(symbol for symbol, pair in _FRANKFURTER_PAIRS.items() if pair in pairs)
    if not symbols:
        return []
    url = f"{_FRANKFURTER_URL}/{start.isoformat()}..{end.isoformat()}?base=USD&symbols={symbols}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ExchangeRateHistoryUnavailable(f"Frankfurter range: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise ExchangeRateHistoryUnavailable("Frankfurter range: unexpected body")
    return parse_frankfurter_range(data, start, end)


# --- Provider registries ---

EXCHANGE_RATE_PROVIDERS = [
    ExchangeRateProviderInfo("dolarapi", fetch_dolarapi),
    ExchangeRateProviderInfo("frankfurter", fetch_frankfurter),
]

# Together they cover every ExchangeRatePair, each pair exactly once.
EXCHANGE_RATE_HISTORY_PROVIDERS = [
    ExchangeRateHistoryProviderInfo(
        "argentinadatos",
        (ExchangeRatePair.USD_ARS_OFICIAL, ExchangeRatePair.USD_ARS_BLUE, ExchangeRatePair.USD_ARS_MEP),
        fetch_argentinadatos_history,
    ),
    ExchangeRateHistoryProviderInfo(
        "frankfurter",
        (ExchangeRatePair.USD_BRL, ExchangeRatePair.USD_EUR, ExchangeRatePair.USD_GBP),
        fetch_frankfurter_history,
    ),
]
