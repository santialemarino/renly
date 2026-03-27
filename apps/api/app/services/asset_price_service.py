# Business logic for asset prices: fetching from providers and storing in the DB.

import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_price import AssetPrice
from app.models.investment import InvestmentCategory
from app.repositories.asset_price_repository import asset_price_repository
from app.services import price_providers
from app.services.price_providers import SOURCE_COINGECKO, SOURCE_YFINANCE

logger = logging.getLogger(__name__)

# Maps investment category to the provider function and source name.
_CATEGORY_PROVIDERS = {
    InvestmentCategory.stocks: (SOURCE_YFINANCE, price_providers.fetch_yfinance),
    InvestmentCategory.cedears: (SOURCE_YFINANCE, price_providers.fetch_yfinance),
    InvestmentCategory.crypto: (SOURCE_COINGECKO, price_providers.fetch_coingecko),
}


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


# Fetches prices from the appropriate provider and stores them in the DB.
# Returns the number of prices stored.
async def fetch_and_store_prices(
    session: AsyncSession,
    ticker: str,
    category: InvestmentCategory,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> int:
    provider_info = _CATEGORY_PROVIDERS.get(category)
    if provider_info is None:
        logger.warning("No price provider for category %s (ticker: %s).", category, ticker)
        return 0

    source_name, fetch_fn = provider_info

    if source_name == SOURCE_COINGECKO:
        results = await fetch_fn(ticker)
    else:
        results = await fetch_fn(ticker, start_date, end_date)

    if not results:
        logger.info("No prices returned for %s from %s.", ticker, source_name)
        return 0

    count = 0
    for price_date, price, currency in results:
        asset_price = AssetPrice(
            ticker=ticker,
            date=price_date,
            price=price,
            currency=currency,
            source=source_name,
        )
        await asset_price_repository.upsert(session, asset_price)
        count += 1

    logger.info("Stored %d prices for %s from %s.", count, ticker, source_name)
    return count


# Fetches prices for all ticker-linked investments. Returns total prices stored.
async def refresh_all_prices(session: AsyncSession) -> int:
    from app.repositories.investment_repository import investment_repository

    investments = await investment_repository.list_with_ticker(session)
    total = 0
    for inv in investments:
        try:
            count = await fetch_and_store_prices(session, inv.ticker, inv.category)
            total += count
        except Exception:
            logger.exception("Failed to fetch prices for %s (%s).", inv.ticker, inv.name)
    return total
