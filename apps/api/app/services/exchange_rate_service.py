# Business logic for exchange rates: querying stored rates and fetching from providers.
# Provider-specific logic (URLs, parsing, field mapping) lives in exchange_rate_providers.py.

import asyncio
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


# Fetches latest rates from all registered providers in parallel and stores them.
async def fetch_and_store_latest(session: AsyncSession) -> list[ExchangeRate]:
    today = date_type.today()

    # Fetch from all providers in parallel.
    fetch_results = await asyncio.gather(
        *[provider.fetch() for provider in EXCHANGE_RATE_PROVIDERS],
        return_exceptions=True,
    )

    # Collect all (pair, rate, source) tuples for bulk upsert.
    all_rates: list[tuple] = []
    for provider, results in zip(EXCHANGE_RATE_PROVIDERS, fetch_results):
        if isinstance(results, BaseException):
            logger.exception("Provider %s failed: %s.", provider.source, results)
            continue
        for pair, rate_value in results:
            all_rates.append((pair, rate_value, provider.source))
        if results:
            logger.info("Fetched %d rates from %s.", len(results), provider.source)

    if not all_rates:
        return []

    await exchange_rate_repository.bulk_upsert(session, all_rates, today)
    await session.commit()

    # Return stored rates for logging/caller.
    stored = await exchange_rate_repository.get_by_date(session, today)
    logger.info("Stored %d exchange rates for %s.", len(stored), today)
    return stored
