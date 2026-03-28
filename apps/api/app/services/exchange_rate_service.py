# Business logic for exchange rates: querying stored rates and fetching from providers.
# Provider-specific logic (URLs, parsing, field mapping) lives in exchange_rate_providers.py.

import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange_rate import ExchangeRate
from app.repositories.exchange_rate_repository import exchange_rate_repository
from app.schemas.exchange_rate import ExchangeRateResponse, LatestRatesResponse
from app.services.exchange_rate_providers import EXCHANGE_RATE_PROVIDERS

logger = logging.getLogger(__name__)


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


# Fetches latest rates from all registered providers and stores them.
async def fetch_and_store_latest(session: AsyncSession) -> list[ExchangeRate]:
    today = date_type.today()
    stored: list[ExchangeRate] = []

    for provider in EXCHANGE_RATE_PROVIDERS:
        results = await provider.fetch()
        for pair, rate_value in results:
            rate = ExchangeRate(
                date=today,
                pair=pair,
                rate=rate_value,
                source=provider.source,
            )
            stored.append(await exchange_rate_repository.upsert(session, rate))

        if results:
            logger.info("Stored %d rates from %s for %s.", len(results), provider.source, today)

    return stored
