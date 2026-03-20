# Business logic for exchange rates: querying stored rates and fetching from DolarApi.

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


# Fetches latest rates from DolarApi and stores them in the DB.
async def fetch_and_store_latest(session: AsyncSession) -> list[ExchangeRate]:
    data = await _fetch_dolarapi()
    if data is None:
        return []
    today = date_type.today()
    return await _store_dolarapi_rates(session, data, today)


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
