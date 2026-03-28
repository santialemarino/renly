# Exchange rate provider implementations for fetching rates from external APIs.
# Each provider returns a list of (pair, rate) tuples.
# Providers are stateless — they fetch and return, the service handles storage.
# To add a new source, create a fetch function and add it to EXCHANGE_RATE_PROVIDERS.

import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import NamedTuple

import httpx

from app.models.exchange_rate import ExchangeRatePair

logger = logging.getLogger(__name__)

# --- Result type ---

ExchangeRateResult = list[tuple[ExchangeRatePair, Decimal]]


# --- Provider metadata ---


# Describes an exchange rate provider: its source name and fetch function.
class ExchangeRateProviderInfo(NamedTuple):
    source: str
    fetch: Callable[..., Awaitable[ExchangeRateResult]]


# --- DolarApi provider (USD/ARS oficial, MEP, blue) ---

_DOLARAPI_URL = "https://dolarapi.com/v1"

# Maps DolarApi "casa" field to ExchangeRatePair.
_CASA_TO_PAIR = {
    "oficial": ExchangeRatePair.USD_ARS_OFICIAL,
    "blue": ExchangeRatePair.USD_ARS_BLUE,
    "bolsa": ExchangeRatePair.USD_ARS_MEP,
}


# Fetches USD/ARS rates (oficial, blue, MEP) from DolarApi.
# Returns the average of compra/venta for each rate type.
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

    results: ExchangeRateResult = []
    for item in data:
        casa = item.get("casa")
        pair = _CASA_TO_PAIR.get(casa)
        if pair is None:
            continue

        compra = item.get("compra")
        venta = item.get("venta")
        if compra is None or venta is None:
            continue

        avg = (Decimal(str(compra)) + Decimal(str(venta))) / 2
        results.append((pair, avg))

    if results:
        logger.info("Fetched %d rates from DolarApi.", len(results))

    return results


# --- Frankfurter provider (USD/BRL, USD/EUR, USD/GBP) ---

_FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"

# Maps Frankfurter currency symbols to ExchangeRatePair.
_FRANKFURTER_PAIRS = {
    "BRL": ExchangeRatePair.USD_BRL,
    "EUR": ExchangeRatePair.USD_EUR,
    "GBP": ExchangeRatePair.USD_GBP,
}


# Fetches USD-based rates (BRL, EUR, GBP) from Frankfurter (ECB data).
# Frankfurter returns rates as "1 USD = X <currency>", matching our storage convention.
async def fetch_frankfurter() -> ExchangeRateResult:
    symbols = ",".join(_FRANKFURTER_PAIRS.keys())
    url = f"{_FRANKFURTER_URL}?base=USD&symbols={symbols}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        logger.exception("Failed to fetch from Frankfurter: %s.", url)
        return []

    results: ExchangeRateResult = []
    rates = data.get("rates", {})
    for symbol, pair in _FRANKFURTER_PAIRS.items():
        value = rates.get(symbol)
        if value is None:
            continue
        results.append((pair, Decimal(str(value))))

    if results:
        logger.info("Fetched %d rates from Frankfurter.", len(results))

    return results


# --- Provider registry ---

EXCHANGE_RATE_PROVIDERS = [
    ExchangeRateProviderInfo("dolarapi", fetch_dolarapi),
    ExchangeRateProviderInfo("frankfurter", fetch_frankfurter),
]
