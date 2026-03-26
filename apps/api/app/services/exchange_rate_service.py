# Business logic for exchange rates: querying stored rates, fetching from DolarApi and Frankfurter.

import logging
from datetime import date as date_type
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.repositories.exchange_rate_repository import exchange_rate_repository
from app.schemas.exchange_rate import ExchangeRateResponse, LatestRatesResponse

logger = logging.getLogger(__name__)

# Maps DolarApi "casa" field to our ExchangeRatePair enum.
_CASA_TO_PAIR = {
    "oficial": ExchangeRatePair.USD_ARS_OFICIAL,
    "blue": ExchangeRatePair.USD_ARS_BLUE,
    "bolsa": ExchangeRatePair.USD_ARS_MEP,
}

# Frankfurter currency symbols and their ExchangeRatePair.
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
_FRANKFURTER_PAIRS = {
    "BRL": ExchangeRatePair.USD_BRL,
    "EUR": ExchangeRatePair.USD_EUR,
    "GBP": ExchangeRatePair.USD_GBP,
}


# Returns the latest rates from the DB for all pairs.
async def get_latest_rates(session: AsyncSession) -> LatestRatesResponse:
    latest_map = await exchange_rate_repository.get_latest_all(session)
    rates = [ExchangeRateResponse.model_validate(r) for r in latest_map.values()]
    last_update = max((r.date for r in rates), default=None)
    return LatestRatesResponse(rates=rates, last_update=last_update)


# Returns all rates for a specific date.
async def get_rates_by_date(
    session: AsyncSession,
    rate_date: date_type,
) -> list[ExchangeRateResponse]:
    rates = await exchange_rate_repository.get_by_date(session, rate_date)
    return [ExchangeRateResponse.model_validate(r) for r in rates]


# Fetches latest rates from all sources (DolarApi + Frankfurter) and stores them.
async def fetch_and_store_latest(session: AsyncSession) -> list[ExchangeRate]:
    today = date_type.today()
    stored: list[ExchangeRate] = []

    dolar_data = await _fetch_dolarapi()
    if dolar_data is not None:
        stored.extend(await _store_dolarapi_rates(session, dolar_data, today))

    frankfurter_data = await _fetch_frankfurter()
    if frankfurter_data is not None:
        stored.extend(await _store_frankfurter_rates(session, frankfurter_data, today))

    return stored


# Calls DolarApi GET /v1/dolares. Returns the parsed JSON array or None on failure.
async def _fetch_dolarapi() -> list[dict] | None:
    url = f"{settings.dolarapi_url}/dolares"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        logger.exception("Failed to fetch from DolarApi: %s", url)
        return None


# Parses DolarApi response and upserts oficial, blue, and MEP rates.
async def _store_dolarapi_rates(
    session: AsyncSession,
    data: list[dict],
    rate_date: date_type,
) -> list[ExchangeRate]:
    stored: list[ExchangeRate] = []

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

        rate = ExchangeRate(
            date=rate_date,
            pair=pair,
            rate=avg,
            source="dolarapi",
        )
        stored.append(await exchange_rate_repository.upsert(session, rate))

    if stored:
        logger.info("Stored %d DolarApi rates for %s.", len(stored), rate_date)

    return stored


# Calls Frankfurter GET /v1/latest?base=USD. Returns parsed JSON or None on failure.
async def _fetch_frankfurter() -> dict | None:
    symbols = ",".join(_FRANKFURTER_PAIRS.keys())
    url = f"{FRANKFURTER_URL}?base=USD&symbols={symbols}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        logger.exception("Failed to fetch from Frankfurter: %s", url)
        return None


# Parses Frankfurter response and upserts EUR, GBP, BRL rates.
# Frankfurter returns rates as "1 USD = X <currency>", which matches our storage convention.
async def _store_frankfurter_rates(
    session: AsyncSession,
    data: dict,
    rate_date: date_type,
) -> list[ExchangeRate]:
    stored: list[ExchangeRate] = []
    rates = data.get("rates", {})

    for symbol, pair in _FRANKFURTER_PAIRS.items():
        value = rates.get(symbol)
        if value is None:
            continue

        rate = ExchangeRate(
            date=rate_date,
            pair=pair,
            rate=Decimal(str(value)),
            source="frankfurter",
        )
        stored.append(await exchange_rate_repository.upsert(session, rate))

    if stored:
        logger.info("Stored %d Frankfurter rates for %s.", len(stored), rate_date)

    return stored
