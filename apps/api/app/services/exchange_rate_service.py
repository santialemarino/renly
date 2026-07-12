# Business logic for exchange rates: querying stored rates and fetching from providers.
# Provider-specific logic (URLs, parsing, field mapping) lives in exchange_rate_providers.py.

import asyncio
import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.currency import SUPPORTED_CURRENCIES
from app.models.exchange_rate import ExchangeRate
from app.repositories.exchange_rate_repository import exchange_rate_repository
from app.schemas.exchange_rate import ExchangeRateResponse, LatestRatesResponse, SupportedCurrenciesResponse
from app.services import settings_service
from app.services.exchange_rate_providers import EXCHANGE_RATE_PROVIDERS
from app.utils.metrics import RateLookup

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


# Returns the currency codes with exchange-rate support, from the domain registry (the single
# source of truth). No DB access — entry forms build their currency picker from this.
def get_supported_currencies() -> SupportedCurrenciesResponse:
    return SupportedCurrenciesResponse(currencies=sorted(SUPPORTED_CURRENCIES))


# Builds a RateLookup pre-loaded with every stored exchange rate. One DB round-trip;
# callers reuse the returned object across many per-row lookups within a request.
async def build_rate_lookup(
    session: AsyncSession,
    dollar_preference: str | None = None,
) -> RateLookup:
    rates_by_pair = await exchange_rate_repository.get_all_grouped_by_pair(session)
    return RateLookup(dollar_preference, rates_by_pair)


# Builds the per-request RateLookup honoring the user's dollar-rate preference. The single
# entry point converting services use; build ONE per request and pass it down to composed
# service calls so the rates table is never loaded twice for the same request.
async def get_user_rate_lookup(session: AsyncSession, user_id: int) -> RateLookup:
    dollar_preference = await settings_service.get_dollar_pref(session, user_id)
    return await build_rate_lookup(session, dollar_preference)


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
