# Business logic for asset prices: fetching from providers and storing in the DB.

import asyncio
import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_price import AssetPrice
from app.models.investment import Investment, InvestmentCategory
from app.repositories.asset_price_repository import asset_price_repository
from app.schemas.asset_price import PriceLookupResponse
from app.services import exchange_rate_service, price_providers
from app.services.price_providers import PriceProviderInfo, PriceResult
from app.utils import metrics as mh

logger = logging.getLogger(__name__)

# Maps investment category to its price provider.
# To swap a provider for a category, change the entry here.
_CATEGORY_PROVIDERS: dict[InvestmentCategory, PriceProviderInfo] = {
    InvestmentCategory.cedears: PriceProviderInfo(
        source=price_providers.SOURCE_YFINANCE,
        fetch=price_providers.fetch_yfinance,
        supports_history=True,
    ),
    InvestmentCategory.crypto: PriceProviderInfo(
        source=price_providers.SOURCE_COINGECKO,
        fetch=price_providers.fetch_coingecko,
        supports_history=False,
    ),
    InvestmentCategory.government_bonds: PriceProviderInfo(
        source=price_providers.SOURCE_YFINANCE,
        fetch=price_providers.fetch_yfinance,
        supports_history=True,
    ),
    InvestmentCategory.stocks: PriceProviderInfo(
        source=price_providers.SOURCE_YFINANCE,
        fetch=price_providers.fetch_yfinance,
        supports_history=True,
    ),
    InvestmentCategory.fci: PriceProviderInfo(
        source=price_providers.SOURCE_CAFCI,
        fetch=price_providers.fetch_fci,
        supports_history=False,
    ),
}

# Maximum concurrent provider fetches during a refresh. Bounds the parallel fan-out so a large
# investment count can't trip provider rate limits (rate-limit failures silently drop prices).
MAX_CONCURRENT_PRICE_FETCHES = 8


# Returns the latest stored price for a ticker. Returns None if not found.
async def get_latest_price(
    session: AsyncSession,
    ticker: str,
) -> AssetPrice | None:
    return await asset_price_repository.get_latest(session, ticker)


# Returns the price for a ticker on a specific date. Returns None if not found.
async def get_price_by_date(
    session: AsyncSession,
    ticker: str,
    price_date: date_type,
) -> AssetPrice | None:
    return await asset_price_repository.get_by_ticker_and_date(session, ticker, price_date)


# Returns price history for a ticker, optionally filtered by date range.
async def get_price_history(
    session: AsyncSession,
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> list[AssetPrice]:
    return await asset_price_repository.get_history(session, ticker, start_date, end_date)


# Returns the price for a ticker on a date. Fetches from provider if not in DB.
# Best-effort: returns None if the provider has no data for that date.
async def get_or_fetch_price(
    session: AsyncSession,
    ticker: str,
    category: InvestmentCategory,
    price_date: date_type,
) -> AssetPrice | None:
    existing = await asset_price_repository.get_by_ticker_and_date(session, ticker, price_date)
    if existing is not None:
        return existing
    # Not in DB — try to fetch from provider for that date range.
    await fetch_and_store_prices(session, ticker, category, price_date, price_date)
    return await asset_price_repository.get_by_ticker_and_date(session, ticker, price_date)


# Returns the price for a ticker on a date as the lookup response, converting to convert_to
# when requested. Conversion uses the rate at the price's own historical date (Phase 3,
# Step C): a January price displayed in USD uses January's rate, not today's.
# Returns None when no price could be found or fetched.
async def lookup_price(
    session: AsyncSession,
    user_id: int,
    ticker: str,
    category: InvestmentCategory,
    price_date: date_type,
    convert_to: str | None,
) -> PriceLookupResponse | None:
    price = await get_or_fetch_price(session, ticker, category, price_date)
    if price is None:
        return None

    converted_price = None
    converted_currency = None
    if convert_to and convert_to != price.currency:
        lookup = await exchange_rate_service.get_user_rate_lookup(session, user_id)
        rate_map = lookup.get_rate_map_at(price.date)
        if rate_map and mh.can_convert(price.currency, convert_to):
            converted_price = mh.convert_value(price.price, price.currency, convert_to, rate_map)
    if converted_price is not None:
        converted_currency = convert_to

    return PriceLookupResponse(
        ticker=price.ticker,
        date=price.date,
        price=price.price,
        currency=price.currency,
        converted_price=converted_price,
        converted_currency=converted_currency,
        source=price.source,
    )


# Fetches prices from the appropriate provider and stores them in the DB.
# Returns the number of prices stored.
async def fetch_and_store_prices(
    session: AsyncSession,
    ticker: str,
    category: InvestmentCategory,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> int:
    provider = _CATEGORY_PROVIDERS.get(category)
    if provider is None:
        logger.warning("No price provider for category %s (ticker: %s).", category, ticker)
        return 0

    results = await provider.fetch(ticker, start_date, end_date)

    if not results:
        logger.info("No prices returned for %s from %s.", ticker, provider.source)
        return 0

    prices = [AssetPrice(ticker=ticker, date=d, price=p, currency=c, source=provider.source) for d, p, c in results]
    count = await asset_price_repository.bulk_upsert(session, prices)
    await session.commit()

    logger.info("Stored %d prices for %s from %s.", count, ticker, provider.source)
    return count


# Fetches prices for all ticker-linked investments in the DB in parallel. Returns total prices stored.
# System-wide refresh — reserved for the scheduler job. User-triggered refreshes use refresh_user_prices.
async def refresh_all_prices(session: AsyncSession) -> int:
    from app.repositories.investment_repository import investment_repository

    investments = await investment_repository.list_with_ticker(session)
    return await _refresh_prices_for_investments(session, investments)


# Fetches prices for the user's ticker-linked investments in parallel. Returns total prices stored.
async def refresh_user_prices(session: AsyncSession, user_id: int) -> int:
    from app.repositories.investment_repository import investment_repository

    investments = await investment_repository.list_with_ticker_by_user(session, user_id)
    return await _refresh_prices_for_investments(session, investments)


# Fetches prices for the given ticker-linked investments and stores them. Returns total prices stored.
# Deduplicates to unique (ticker, category) pairs first — N holders of the same ticker cost one
# provider fetch, not N — and bounds fetch concurrency with a semaphore. Prices are stored per
# ticker (asset_prices is keyed by ticker, not investment), so one upsert per unique pair covers
# every investment sharing that ticker.
async def _refresh_prices_for_investments(session: AsyncSession, investments: list[Investment]) -> int:
    # Clear per-cycle caches so providers re-download fresh data.
    price_providers.clear_fci_cache()

    unique_pairs = {(inv.ticker, inv.category) for inv in investments if inv.ticker}
    pairs = sorted((ticker, category) for ticker, category in unique_pairs if category in _CATEGORY_PROVIDERS)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PRICE_FETCHES)

    # Fetch prices from external APIs in bounded parallel (no DB access in fetch functions).
    async def _fetch_one(ticker: str, category: InvestmentCategory) -> PriceResult:
        provider = _CATEGORY_PROVIDERS[category]
        try:
            async with semaphore:
                return await provider.fetch(ticker, None, None)
        except Exception:
            logger.exception("Failed to fetch prices for %s (%s).", ticker, category)
            return []

    fetch_results = await asyncio.gather(*[_fetch_one(ticker, category) for ticker, category in pairs])

    # Store results sequentially (DB writes share one session).
    total = 0
    for (ticker, category), results in zip(pairs, fetch_results):
        if not results:
            continue
        provider = _CATEGORY_PROVIDERS[category]
        prices = [AssetPrice(ticker=ticker, date=d, price=p, currency=c, source=provider.source) for d, p, c in results]
        total += await asset_price_repository.bulk_upsert(session, prices)

    if total:
        await session.commit()
        logger.info("Refreshed prices: %d prices across %d unique tickers (%d investments).", total, len(pairs), len(investments))
    return total
