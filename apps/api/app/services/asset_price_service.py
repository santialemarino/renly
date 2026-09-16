# Business logic for asset prices: fetching from providers and storing in the DB.

import asyncio
import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_price import AssetPrice
from app.models.investment import Investment, InvestmentCategory
from app.repositories.asset_price_repository import asset_price_repository
from app.schemas.asset_price import AssetPriceListResponse, AssetPriceResponse, PriceLookupResponse
from app.services import exchange_rate_service, price_providers
from app.services.price_providers import PriceProviderInfo, PriceResult
from app.utils import metrics as mh
from app.utils.pagination import DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)

# The providers for each category, in the order the chain tries them (INFRA-9).
#
# First entry is the primary; the rest are fallbacks, reached only when the one before it could not
# ANSWER (PriceProviderUnavailable) — never when it answered that the ticker has no price. To change
# where a category's prices come from, reorder or edit its tuple; nothing else in the service knows a
# provider's name.
#
# Each chain is built from what the providers actually cover, which differs by market: the US-equity
# APIs know nothing about BYMA, and data912 knows nothing but BYMA.
#
# Every fallback here is independent of the primary it backs, and that is a requirement rather than a
# coincidence. Calling Yahoo's chart endpoint directly was the obvious extra leg for the equity chains
# — same data, no library — and measuring it is what disqualified it: the raw endpoint answers 429 for
# this host while yfinance, which negotiates a cookie and crumb first, succeeds against the same
# upstream in the same second. A fallback that fails whenever it is reached is worse than no fallback,
# because it costs a round trip and reports an outage that is its own.
_YFINANCE = PriceProviderInfo(
    source=price_providers.SOURCE_YFINANCE,
    fetch=price_providers.fetch_yfinance,
    supports_history=True,
)
_FINNHUB = PriceProviderInfo(
    source=price_providers.SOURCE_FINNHUB,
    fetch=price_providers.fetch_finnhub,
    supports_history=False,
    is_configured=price_providers.finnhub_is_configured,
)
_DATA912 = PriceProviderInfo(
    source=price_providers.SOURCE_DATA912,
    fetch=price_providers.fetch_data912,
    supports_history=False,
)

_CATEGORY_PROVIDERS: dict[InvestmentCategory, tuple[PriceProviderInfo, ...]] = {
    InvestmentCategory.cedears: (_YFINANCE, _DATA912),
    InvestmentCategory.crypto: (
        PriceProviderInfo(
            source=price_providers.SOURCE_COINGECKO,
            fetch=price_providers.fetch_coingecko,
            supports_history=False,
        ),
        PriceProviderInfo(
            source=price_providers.SOURCE_COINBASE,
            fetch=price_providers.fetch_coinbase,
            supports_history=True,
        ),
    ),
    InvestmentCategory.government_bonds: (_YFINANCE, _DATA912),
    InvestmentCategory.stocks: (_YFINANCE, _FINNHUB),
    InvestmentCategory.fci: (
        PriceProviderInfo(
            source=price_providers.SOURCE_CAFCI,
            fetch=price_providers.fetch_cafci,
            supports_history=False,
        ),
        PriceProviderInfo(
            source=price_providers.SOURCE_ARGENTIADATOS,
            fetch=price_providers.fetch_argentinadatos,
            supports_history=False,
        ),
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


# Returns one page of a ticker's price history, optionally filtered by date range.
async def get_price_history(
    session: AsyncSession,
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AssetPriceListResponse:
    prices, total = await asset_price_repository.get_history(session, ticker, start_date, end_date, page=page, page_size=page_size)
    return AssetPriceListResponse(
        items=[AssetPriceResponse.model_validate(p) for p in prices],
        total=total,
        page=page,
        page_size=page_size,
    )


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


# The prices for a ticker and the source that actually served them, or None when no provider could.
#
# Walks the category's chain and stops at the first provider that ANSWERS — an empty answer included,
# because "this ticker has no price today" is a real answer and asking the next provider the same
# question would only produce a second no. Only PriceProviderUnavailable advances the chain.
#
# Returning the source alongside the rows is what keeps the stored source honest. Reading it from the
# map instead is how every FCI price served by the ArgentinaDatos fallback came to be written down as
# "cafci" — the row recorded which provider was SUPPOSED to answer, not which one did.
async def _fetch_through_chain(
    ticker: str,
    category: InvestmentCategory,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> tuple[PriceResult, str] | None:
    chain = _CATEGORY_PROVIDERS.get(category)
    if not chain:
        logger.warning("No price provider for category %s (ticker: %s).", category, ticker)
        return None

    wants_history = start_date is not None and end_date is not None
    attempted = False
    for provider in chain:
        # A provider needing a credential nobody set is not a failure — it is simply not part of this
        # deployment's chain, and logging it as an error every cycle would train people to ignore it.
        if not provider.is_configured():
            continue
        # A live-quote provider cannot answer "what did this cost in January", and answering for today
        # instead would be a wrong answer rather than a missing one.
        if wants_history and not provider.supports_history:
            continue
        attempted = True
        try:
            return await provider.fetch(ticker, start_date, end_date), provider.source
        except price_providers.PriceProviderUnavailable as exc:
            logger.warning("Price provider %s unavailable for %s: %s", provider.source, ticker, exc)

    # Every provider that could have answered failed. This is the outcome INFRA-9 exists to make
    # visible: prices simply stop updating, the app keeps rendering the last stored value, and until
    # now the only trace was one warning per provider with nothing saying the ticker went unpriced.
    if attempted:
        logger.error(
            "All %d price providers failed for %s (%s) — the stored price is now stale.",
            len(chain),
            ticker,
            category.value,
        )
    else:
        logger.warning("No usable price provider for %s (%s) with the requested date range.", ticker, category.value)
    return None


# Fetches prices through the category's provider chain and stores them in the DB.
# Returns the number of prices stored.
async def fetch_and_store_prices(
    session: AsyncSession,
    ticker: str,
    category: InvestmentCategory,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> int:
    fetched = await _fetch_through_chain(ticker, category, start_date, end_date)
    if fetched is None:
        return 0
    results, source = fetched

    if not results:
        logger.info("No prices returned for %s from %s.", ticker, source)
        return 0

    prices = [AssetPrice(ticker=ticker, date=d, price=p, currency=c, source=source) for d, p, c in results]
    count = await asset_price_repository.bulk_upsert(session, prices)
    await session.commit()

    logger.info("Stored %d prices for %s from %s.", count, ticker, source)
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
    price_providers.clear_data912_cache()

    unique_pairs = {(inv.ticker, inv.category) for inv in investments if inv.ticker}
    pairs = sorted((ticker, category) for ticker, category in unique_pairs if category in _CATEGORY_PROVIDERS)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PRICE_FETCHES)

    # Fetch prices from external APIs in bounded parallel (no DB access in fetch functions).
    # Returns the rows paired with the source that served them, or None when the whole chain failed.
    async def _fetch_one(ticker: str, category: InvestmentCategory) -> tuple[PriceResult, str] | None:
        async with semaphore:
            return await _fetch_through_chain(ticker, category)

    fetch_results = await asyncio.gather(*[_fetch_one(ticker, category) for ticker, category in pairs])

    # Store results sequentially (DB writes share one session).
    total = 0
    unpriced: list[str] = []
    for (ticker, _category), fetched in zip(pairs, fetch_results):
        if fetched is None:
            unpriced.append(ticker)
            continue
        results, source = fetched
        if not results:
            continue
        prices = [AssetPrice(ticker=ticker, date=d, price=p, currency=c, source=source) for d, p, c in results]
        total += await asset_price_repository.bulk_upsert(session, prices)

    if total:
        await session.commit()
        logger.info("Refreshed prices: %d prices across %d unique tickers (%d investments).", total, len(pairs), len(investments))

    # One line naming every ticker left on a stale price, rather than N scattered provider warnings
    # that never add up to "the refresh did not do its job".
    if unpriced:
        logger.error(
            "Price refresh left %d of %d tickers unpriced (every provider failed): %s",
            len(unpriced),
            len(pairs),
            ", ".join(unpriced),
        )
    return total
