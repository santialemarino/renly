# Business logic for exchange rates: querying stored rates and fetching from providers.
# Provider-specific logic (URLs, parsing, field mapping) lives in exchange_rate_providers.py.

import asyncio
import logging
import time
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.currency import SUPPORTED_CURRENCIES
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.repositories.exchange_rate_repository import exchange_rate_repository
from app.schemas.exchange_rate import ExchangeRateResponse, LatestRatesResponse, SupportedCurrenciesResponse
from app.services import settings_service
from app.services.exchange_rate_providers import EXCHANGE_RATE_PROVIDERS
from app.utils.metrics import RateLookup

logger = logging.getLogger(__name__)

# Process-level TTL cache for the grouped-rates load that backs every RateLookup. Rates are global
# (not per-user) and only change when the 6-hourly scheduler stores fresh quotes, so a short TTL
# plus the explicit invalidation below stops every converting endpoint from re-reading the whole
# exchange_rates table per request (a dashboard view = up to 7 full-table loads today). Cached
# entries are detached, relationship-free ORM rows used read-only — safe to share across requests;
# if ExchangeRate ever grows a relationship(), revisit this cache first.
RATES_CACHE_TTL_SECONDS = 600

_rates_cache: dict[ExchangeRatePair, list[ExchangeRate]] | None = None
_rates_cache_loaded_at: float | None = None


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


# Returns every stored rate grouped by pair (sorted by date ascending), serving a cached copy for
# up to RATES_CACHE_TTL_SECONDS. No single-flight: concurrent misses each load once (harmless).
# Returns the cached dict itself — callers must treat it as read-only.
async def get_rates_grouped_by_pair_cached(session: AsyncSession) -> dict[ExchangeRatePair, list[ExchangeRate]]:
    global _rates_cache, _rates_cache_loaded_at
    now = time.monotonic()
    if _rates_cache is not None and _rates_cache_loaded_at is not None and now - _rates_cache_loaded_at < RATES_CACHE_TTL_SECONDS:
        return _rates_cache
    _rates_cache = await exchange_rate_repository.get_all_grouped_by_pair(session)
    _rates_cache_loaded_at = now
    return _rates_cache


# Drops the cached rates so the next lookup reloads. Called right after the scheduler stores fresh
# rates; any other process (multi-worker deploys) falls back to the TTL bound.
def invalidate_rates_cache() -> None:
    global _rates_cache, _rates_cache_loaded_at
    _rates_cache = None
    _rates_cache_loaded_at = None


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
    rates_by_pair = await get_rates_grouped_by_pair_cached(session)
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

    # Fresh rates just landed — serve them immediately instead of waiting out the TTL.
    invalidate_rates_cache()

    # Return stored rates for logging/caller.
    stored = await exchange_rate_repository.get_by_date(session, today)
    logger.info("Stored %d exchange rates for %s.", len(stored), today)
    return stored
