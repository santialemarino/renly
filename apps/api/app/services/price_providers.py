# Price provider implementations for fetching asset prices from external APIs.
# Each provider has the same signature: (ticker, start_date?, end_date?) -> PriceResult.
# Providers are stateless — they fetch and return, the service handles storage.
# To swap a provider or change its fallbacks, edit the chain in asset_price_service._CATEGORY_PROVIDERS.
#
# A provider reports the two outcomes SEPARATELY (INFRA-9), and that distinction is the whole basis of
# the fallback chain: an empty list means "this provider is fine and the ticker genuinely has no price
# for that range" (a weekend, a delisting), while PriceProviderUnavailable means "this provider could
# not answer" — and only the second is a reason to try the next provider. Returning [] for both, as
# every provider here used to, made a rate-limited API indistinguishable from a quiet market, so a
# chain built on it would walk every provider on every weekend and still could not report an outage.

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal
from typing import NamedTuple

import httpx

logger = logging.getLogger(__name__)

# --- Result types ---

PriceResult = list[tuple[date_type, Decimal, str]]

# CEDEAR ratio result: (ticker, underlying, ratio).
RatioResult = list[tuple[str, str, Decimal]]


# CEDEAR ratio fetch result: ratios + source date (if parseable).
class RatioFetchResult(NamedTuple):
    ratios: RatioResult
    source_date: date_type | None


# --- Provider metadata ---


# Raised by a provider that could not answer at all — an HTTP error, a rate limit, an unparseable
# payload, a missing credential. Distinct from returning [], which asserts the provider DID answer and
# the ticker has no price. The chain advances on this and only this.
class PriceProviderUnavailable(Exception):
    pass


# How an httpx failure is described in a PriceProviderUnavailable message — and therefore in the log
# line the refresh writes, and in Sentry when a DSN is configured.
#
# The exception's own `str()` is deliberately not used: httpx builds it from the FULL request URL, so
# any credential a provider takes as a query parameter is reproduced verbatim in the message. That is
# how the Finnhub key reached the logs. The class name and the status code are what an operator
# actually needs ("the provider answered 401", not "the market is quiet"), and they carry nothing
# that has to be redacted afterwards.
#
# Scope worth being exact about: this sanitises the MESSAGE. `raise ... from exc` still chains the
# original, so a handler that printed a full traceback would surface the URL again. None does today —
# PriceProviderUnavailable is caught in exactly one place and formatted with %s — but that is a
# property of the current callers, not something this helper can enforce.
def _describe_http_failure(exc: Exception) -> str:
    # Only HTTPStatusError builds its message from the request URL — a ConnectError, a ReadTimeout or
    # a KeyError out of a provider's own parsing all stringify to something that carries no URL and
    # therefore no credential. Those keep their message: dropping it would trade a real leak for a
    # real loss, and the yfinance path (a bare `except Exception` around Renly's own row mapping) is
    # the one the chain's own comment calls the failure it most expects. "Exception" alone, with no
    # message and no traceback, is not something anybody can debug from.
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        return f"{type(exc).__name__} (HTTP {status})" if status is not None else type(exc).__name__
    return f"{type(exc).__name__}: {exc}"


# Describes a price provider: its source name, fetch function, and capabilities.
# is_configured answers whether the provider can run at all in this deployment — a provider needing a
# credential that is unset is SKIPPED by the chain rather than counted as a failure, so an optional
# provider nobody has provisioned does not log an error on every refresh.
class PriceProviderInfo(NamedTuple):
    source: str
    fetch: Callable[..., Awaitable[PriceResult]]
    supports_history: bool
    is_configured: Callable[[], bool] = lambda: True


# --- Source name constants (stored in the source column of asset_prices/cedear_ratios) ---

SOURCE_YFINANCE = "yfinance"
SOURCE_FINNHUB = "finnhub"
SOURCE_COINGECKO = "coingecko"
SOURCE_COINBASE = "coinbase"
SOURCE_DATA912 = "data912"
SOURCE_CAFCI = "cafci"
COMAFI_SOURCE = "comafi"
BYMA_SOURCE = "byma"


# --- Price providers ---


# Fetches prices from Yahoo Finance via yfinance for stocks, CEDEARs, and government bonds.
# Returns daily closing prices for the given period.
async def fetch_yfinance(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    import asyncio

    import yfinance as yf

    def _fetch() -> PriceResult:
        t = yf.Ticker(ticker)
        kwargs: dict = {}
        if start_date and end_date:
            kwargs["start"] = start_date.isoformat()
            # yfinance end date is exclusive — add one day to include the target date.
            kwargs["end"] = (end_date + timedelta(days=1)).isoformat()
        else:
            kwargs["period"] = "5d"
        hist = t.history(**kwargs)
        if hist.empty:
            return []
        # Determine currency from ticker info (fallback to USD).
        try:
            currency = t.info.get("currency", "USD").upper()
        except Exception:
            currency = "USD"
        results: PriceResult = []
        for idx, row in hist.iterrows():
            price_date = idx.date() if hasattr(idx, "date") else idx
            close = row.get("Close")
            if close is not None:
                results.append((price_date, Decimal(str(round(close, 6))), currency))
        return results

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        # The library breaking is the failure this chain most expects: yfinance scrapes an endpoint it
        # does not own, so it breaks independently of Yahoo being up.
        raise PriceProviderUnavailable(f"yfinance fetch failed for {ticker}: {_describe_http_failure(exc)}") from exc


# Crypto symbol → CoinGecko coin id, for the assets a Renly user is realistically holding.
#
# The two crypto providers disagree about what a ticker IS: CoinGecko addresses a coin by its id
# ("bitcoin") and 404s on a symbol, while Coinbase wants the symbol ("BTC"). Nothing validates the
# ticker on entry, so both spellings exist in real data — a holding stored as "BTC" fetched nothing at
# all, silently, for as long as it had been there. Each provider therefore translates the stored ticker
# into its own vocabulary rather than the user being asked to know either one.
_COINGECKO_IDS_BY_SYMBOL = {
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "BNB": "binancecoin",
    "BTC": "bitcoin",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "ETH": "ethereum",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "SOL": "solana",
    "TRX": "tron",
    "USDC": "usd-coin",
    "USDT": "tether",
    "XRP": "ripple",
}

# The same table read the other way, for providers that address a coin by symbol.
_SYMBOLS_BY_COINGECKO_ID = {coin_id: symbol for symbol, coin_id in _COINGECKO_IDS_BY_SYMBOL.items()}


# The CoinGecko coin id for a stored ticker. An unlisted ticker passes through unchanged, so a coin
# missing from the table still works wherever the stored spelling already matches.
def to_coingecko_id(ticker: str) -> str:
    return _COINGECKO_IDS_BY_SYMBOL.get(ticker.strip().upper(), ticker)


# The exchange symbol for a stored ticker, for providers that address a coin by symbol.
def to_crypto_symbol(ticker: str) -> str:
    cleaned = ticker.strip()
    return _SYMBOLS_BY_COINGECKO_ID.get(cleaned.lower(), cleaned).upper()


# Fetches prices from CoinGecko for crypto assets.
# Accepts either a CoinGecko coin id ("bitcoin") or an exchange symbol ("BTC") — see to_coingecko_id.
# start_date/end_date are accepted for signature uniformity but ignored — CoinGecko
# always returns the last 7 days via the market_chart endpoint.
async def fetch_coingecko(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    url = f"https://api.coingecko.com/api/v3/coins/{to_coingecko_id(ticker)}/market_chart"
    params = {"vs_currency": "usd", "days": "7", "interval": "daily"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise PriceProviderUnavailable(f"CoinGecko fetch failed for {ticker}: {_describe_http_failure(exc)}") from exc

    # CoinGecko reports a rate limit as HTTP 200 with the error in the BODY, so raise_for_status()
    # above does not fire and `prices` below is simply absent. Read as an empty answer that is exactly
    # the shape of a coin with no history — which is how a throttled refresh used to look like a quiet
    # market. Verified live: three calls in a row were enough to trip it.
    status = data.get("status")
    if isinstance(status, dict) and status.get("error_code"):
        raise PriceProviderUnavailable(f"CoinGecko rate-limited for {ticker}: {status.get('error_message')}")

    prices = data.get("prices", [])
    results: PriceResult = []
    for timestamp_ms, price in prices:
        price_date = date_type.fromtimestamp(timestamp_ms / 1000)
        results.append((price_date, Decimal(str(round(price, 6))), "USD"))
    return results


# --- Fallback price providers (INFRA-9) ---

# Finnhub quote API. Free tier is 60 calls/minute and needs a key; unset means the chain skips it.
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_TIMEOUT = 15.0
# Finnhub's documented header alternative to the `token` query parameter. See fetch_finnhub for why
# this repo will only ever use the header form.
FINNHUB_TOKEN_HEADER = "X-Finnhub-Token"

# data912: free, keyless Argentine market data — one call returns every symbol on that board.
DATA912_BASE = "https://data912.com/live"
DATA912_BOARDS = ("arg_stocks", "arg_cedears", "arg_bonds")
DATA912_TIMEOUT = 20.0
DATA912_BYMA_SUFFIX = ".BA"

# Coinbase's public spot price. No key, and it accepts a date for a historical close.
COINBASE_SPOT_URL = "https://api.coinbase.com/v2/prices"
COINBASE_TIMEOUT = 15.0


# Whether a Finnhub key is configured. Without one the chain skips the provider entirely.
def finnhub_is_configured() -> bool:
    from app.config import settings

    return bool(settings.finnhub_api_key)


# Fetches the current US-equity quote from Finnhub.
#
# Genuinely independent of Yahoo, which is why it is in the chain at all — but it answers only with a
# CURRENT quote, so it carries no history and the chain skips it for a dated request.
async def fetch_finnhub(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    from app.config import settings

    if not settings.finnhub_api_key:
        raise PriceProviderUnavailable("Finnhub has no API key configured.")

    try:
        async with httpx.AsyncClient(timeout=FINNHUB_TIMEOUT) as client:
            # The key goes in a HEADER, never a query parameter. Finnhub accepts both, but httpx builds
            # an HTTPStatusError's message from the full request URL — so a `?token=` form puts the key
            # into every "provider unavailable" log line the moment Finnhub answers 401 or 429, and from
            # there into Sentry. A header is not part of that message.
            response = await client.get(
                FINNHUB_QUOTE_URL,
                params={"symbol": ticker},
                headers={FINNHUB_TOKEN_HEADER: settings.finnhub_api_key},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise PriceProviderUnavailable(f"Finnhub fetch failed for {ticker}: {_describe_http_failure(exc)}") from exc

    # Finnhub answers an unknown symbol with a 200 and every field zeroed, so a zero current price is
    # "no such symbol" rather than a real quote — an empty answer, not a provider failure.
    current = payload.get("c")
    if not current:
        return []
    return [(date_type.today(), Decimal(str(current)), "USD")]


# One cached snapshot of every data912 board, keyed by symbol. Cleared per refresh cycle like CAFCI's.
_data912_prices: dict[str, Decimal] | None = None
_data912_lock: asyncio.Lock | None = None
# Whether this cycle's download already failed, which is a SEPARATE fact from the cache being empty.
# Without it every ticker falling back to data912 re-attempts the download: measured at 60 requests to
# a service that was already answering 502, for 20 tickers. The amplification grows with the ticker
# count, so it is worst on exactly the multi-user instance this chain exists for.
_data912_load_failed = False


# Lazily creates the data912 download lock (needs a running loop, so not at import).
def _get_data912_lock() -> asyncio.Lock:
    global _data912_lock
    if _data912_lock is None:
        _data912_lock = asyncio.Lock()
    return _data912_lock


# Downloads every data912 board once and caches the last price per symbol.
async def _load_data912_cache() -> None:
    global _data912_prices, _data912_load_failed

    async def _board(name: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=DATA912_TIMEOUT) as client:
            response = await client.get(f"{DATA912_BASE}/{name}")
            response.raise_for_status()
            return response.json()

    # All or nothing, deliberately: `gather` without return_exceptions propagates the first failure, so
    # one dead board discards the other two. Keeping the partial set would be worse than it looks —
    # every symbol on the missing board would then answer "no price", which is an ANSWER and stops the
    # chain, rather than the outage it actually is.
    try:
        boards = await asyncio.gather(*[_board(name) for name in DATA912_BOARDS])
    except (httpx.HTTPError, ValueError) as exc:
        _data912_load_failed = True
        raise PriceProviderUnavailable(f"data912 board download failed: {_describe_http_failure(exc)}") from exc

    prices: dict[str, Decimal] = {}
    for rows in boards:
        for row in rows:
            symbol = (row.get("symbol") or "").strip().upper()
            close = row.get("c")
            if symbol and close:
                prices[symbol] = Decimal(str(close))
    _data912_prices = prices
    logger.info("data912 cache loaded: %d symbols across %d boards.", len(prices), len(DATA912_BOARDS))


# Fetches an Argentine listing's price from data912 (stocks, CEDEARs and bonds).
#
# Covers exactly the tickers Yahoo serves with a `.BA` suffix, which is the gap the other fallbacks
# leave: the US-equity providers know nothing about BYMA. Prices are ARS and the board is a LIVE quote
# carrying no date of its own, so it answers for today only — hence supports_history=False, and the
# chain will not call it for a backdated lookup rather than answering the wrong question.
async def fetch_data912(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    # Renly stores a BYMA listing the way Yahoo spells it (AAPL.BA); data912 uses the bare symbol.
    symbol = ticker.strip().upper().removesuffix(DATA912_BYMA_SUFFIX)

    if _data912_prices is None:
        async with _get_data912_lock():
            # Re-check after the lock — another coroutine may have populated the cache meanwhile, or
            # already discovered the service is down, in which case this ticker must not retry it.
            if _data912_load_failed:
                raise PriceProviderUnavailable("data912 is unavailable for this refresh cycle.")
            if _data912_prices is None:
                await _load_data912_cache()

    price = (_data912_prices or {}).get(symbol)
    if price is None:
        return []
    return [(date_type.today(), price, "ARS")]


# Clears the data912 cache so the next refresh cycle re-downloads the boards.
def clear_data912_cache() -> None:
    global _data912_prices, _data912_load_failed
    _data912_prices = None
    _data912_load_failed = False


# Fetches a crypto spot price from Coinbase's public API.
#
# Keyless and far more generous than CoinGecko's free tier, which is what makes it a real fallback
# rather than a token one. Accepts either spelling of the ticker — see to_crypto_symbol.
async def fetch_coinbase(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    symbol = to_crypto_symbol(ticker)
    # Coinbase dates a spot price by query param; with none it answers for now.
    params = {"date": end_date.isoformat()} if end_date else None
    price_date = end_date or date_type.today()

    try:
        async with httpx.AsyncClient(timeout=COINBASE_TIMEOUT) as client:
            response = await client.get(f"{COINBASE_SPOT_URL}/{symbol}-USD/spot", params=params)
            if response.status_code == 404:
                # Coinbase does not list this asset — it answered, so this is an empty result.
                return []
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise PriceProviderUnavailable(f"Coinbase fetch failed for {symbol}: {_describe_http_failure(exc)}") from exc

    amount = (payload.get("data") or {}).get("amount")
    if not amount:
        return []
    return [(price_date, Decimal(str(amount)), "USD")]


# --- CEDEAR ratio provider ---

# Banco Comafi Excel configuration.
COMAFI_CEDEAR_URL = "https://www.comafi.com.ar/Multimedios/otros/7279.xlsx"
COMAFI_TIMEOUT = 30.0
COMAFI_HEADER_SCAN_MAX_ROW = 15
COMAFI_TICKER_HEADER_KEYWORD = "mercado"
COMAFI_TICKER_HEADER_KEYWORD_2 = "identif"
COMAFI_RATIO_HEADER_KEYWORD = "ratio"
COMAFI_BYMA_SUFFIX = ".BA"
COMAFI_RATIO_SEPARATOR = ":"


# Fetches all CEDEAR ratios from Banco Comafi's Excel file.
# Returns ratios + the internal date from the spreadsheet (for freshness comparison).
async def fetch_comafi_ratios() -> RatioFetchResult:
    import asyncio
    import io

    try:
        async with httpx.AsyncClient(timeout=COMAFI_TIMEOUT) as client:
            response = await client.get(COMAFI_CEDEAR_URL)
            response.raise_for_status()
            content = response.content
    except httpx.HTTPError:
        logger.exception("Comafi CEDEAR Excel fetch failed.")
        return RatioFetchResult([], None)

    def _parse(data: bytes) -> RatioFetchResult:
        import re

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return RatioFetchResult([], None)

        # Parse the internal date from the first rows (e.g., "LISTA TOTAL DE CEDEARS AL  13.03.2025").
        source_date: date_type | None = None
        for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
            for cell in row:
                if isinstance(cell, date_type):
                    source_date = cell
                    break
                if isinstance(cell, str):
                    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", cell)
                    if match:
                        try:
                            source_date = date_type(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                        except ValueError:
                            pass
            if source_date:
                break

        # Find the header row to locate columns dynamically.
        header_row = None
        ticker_col = None
        ratio_col = None
        for row in ws.iter_rows(min_row=1, max_row=COMAFI_HEADER_SCAN_MAX_ROW, values_only=False):
            for cell in row:
                val = str(cell.value or "").strip().lower()
                if COMAFI_TICKER_HEADER_KEYWORD in val and COMAFI_TICKER_HEADER_KEYWORD_2 in val:
                    header_row = cell.row
                    ticker_col = cell.column
                if COMAFI_RATIO_HEADER_KEYWORD in val:
                    ratio_col = cell.column
            if header_row and ticker_col and ratio_col:
                break

        if not header_row or not ticker_col or not ratio_col:
            logger.warning("Could not find header columns in Comafi Excel.")
            wb.close()
            return RatioFetchResult([], source_date)

        results: RatioResult = []
        for row in ws.iter_rows(min_row=header_row + 1, values_only=False):
            ticker_cell = row[ticker_col - 1].value if len(row) >= ticker_col else None
            ratio_cell = row[ratio_col - 1].value if len(row) >= ratio_col else None
            if not ticker_cell or not ratio_cell:
                continue

            ticker_str = str(ticker_cell).strip().upper()
            if not ticker_str:
                continue

            # Parse ratio — formats: "10:1", "10", "10.0".
            ratio_str = str(ratio_cell).strip().replace(",", ".")
            if COMAFI_RATIO_SEPARATOR in ratio_str:
                parts = ratio_str.split(COMAFI_RATIO_SEPARATOR)
                try:
                    ratio_val = Decimal(parts[0].strip()) / Decimal(parts[1].strip())
                except Exception:
                    continue
            else:
                try:
                    ratio_val = Decimal(ratio_str)
                except Exception:
                    continue

            if ratio_val <= 0:
                continue

            # Build BYMA ticker (add .BA suffix if not present).
            cedear_ticker = ticker_str if ticker_str.endswith(COMAFI_BYMA_SUFFIX) else f"{ticker_str}{COMAFI_BYMA_SUFFIX}"
            # Underlying is the ticker without .BA.
            underlying = ticker_str.replace(COMAFI_BYMA_SUFFIX, "")

            results.append((cedear_ticker, underlying, ratio_val))

        wb.close()
        return RatioFetchResult(results, source_date)

    try:
        return await asyncio.to_thread(_parse, content)
    except Exception:
        logger.exception("Failed to parse Comafi CEDEAR Excel.")
        return RatioFetchResult([], None)


# --- BYMA PDF ratio provider ---

BYMA_CEDEARS_PAGE_URL = "https://www.byma.com.ar/productos/productos-financieros/cedears"
BYMA_PDF_CDN_PREFIX = "https://cdn.prod.website-files.com/"
BYMA_TIMEOUT = 30.0
BYMA_RATIO_SEPARATOR = ":"
BYMA_BYMA_SUFFIX = ".BA"


# Fetches all CEDEAR ratios from the BYMA PDF.
# First discovers the current PDF URL from the BYMA page, then parses the PDF.
# Returns ratios + the date from the PDF filename (for freshness comparison).
async def fetch_byma_ratios() -> RatioFetchResult:
    import asyncio

    # Step 1: Discover the PDF URL from the BYMA page.
    try:
        async with httpx.AsyncClient(timeout=BYMA_TIMEOUT, follow_redirects=True) as client:
            page_response = await client.get(BYMA_CEDEARS_PAGE_URL)
            page_response.raise_for_status()
            page_html = page_response.text
    except httpx.HTTPError:
        logger.exception("BYMA CEDEARs page fetch failed.")
        return RatioFetchResult([], None)

    # Find the PDF URL in the page HTML (CDN link with "CEDEARs" in the filename).
    import re

    pdf_match = re.search(
        r'(https://cdn\.prod\.website-files\.com/[^"\']+CEDEARs[^"\']*\.pdf)',
        page_html,
        re.IGNORECASE,
    )
    if not pdf_match:
        logger.warning("Could not find CEDEAR PDF link on BYMA page.")
        return RatioFetchResult([], None)

    pdf_url = pdf_match.group(1)

    # Parse date from the PDF filename (e.g., "BYMA-CEDEARs-2026-02-03.pdf").
    source_date: date_type | None = None
    date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})\.pdf$", pdf_url)
    if date_match:
        try:
            source_date = date_type(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
        except ValueError:
            pass

    # Step 2: Download the PDF.
    try:
        async with httpx.AsyncClient(timeout=BYMA_TIMEOUT) as client:
            pdf_response = await client.get(pdf_url)
            pdf_response.raise_for_status()
            pdf_content = pdf_response.content
    except httpx.HTTPError:
        logger.exception("BYMA CEDEAR PDF download failed: %s", pdf_url)
        return RatioFetchResult([], source_date)

    # Step 3: Parse the PDF.
    def _parse(data: bytes) -> RatioResult:
        import io

        import pdfplumber

        results: RatioResult = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                for line in text.split("\n"):
                    line = line.strip()
                    if not line or "Ratio" in line or "Nombre" in line or "Bolsas y Mercados" in line:
                        continue

                    # Format: "Company Name  TICKER  EXCHANGE  RATIO:1"
                    # The ratio is always at the end, in "N:N" format.
                    ratio_match = re.search(r"(\d+):(\d+)\s*$", line)
                    if not ratio_match:
                        continue

                    # Extract ticker — it's the uppercase word before the exchange name.
                    # Split line into parts and find the ticker.
                    before_ratio = line[: ratio_match.start()].strip()
                    parts = before_ratio.split()
                    if len(parts) < 2:
                        continue

                    # Ticker is typically the second-to-last or third-to-last token before ratio.
                    # The exchange (NYSE, NASDAQ, etc.) is right before the ratio.
                    # Walk backwards: last part = exchange, second-to-last = ticker.
                    ticker = None
                    for i in range(len(parts) - 1, -1, -1):
                        token = parts[i].strip()
                        # Skip exchange names and partial exchange names.
                        if token.upper() in {
                            "NYSE",
                            "NASDAQ",
                            "XETRA",
                            "FRANKFURT",
                            "B3",
                            "ARCA",
                            "GS",
                            "GM",
                            "AMERICAN",
                        }:
                            continue
                        # Found the ticker.
                        ticker = token.upper()
                        break

                    if not ticker or not any(c.isalnum() for c in ticker):
                        continue

                    # Parse ratio.
                    numerator = int(ratio_match.group(1))
                    denominator = int(ratio_match.group(2))
                    if denominator == 0:
                        continue
                    ratio_val = Decimal(numerator) / Decimal(denominator)

                    if ratio_val <= 0:
                        continue

                    cedear_ticker = ticker if ticker.endswith(BYMA_BYMA_SUFFIX) else f"{ticker}{BYMA_BYMA_SUFFIX}"
                    underlying = ticker.replace(BYMA_BYMA_SUFFIX, "")

                    results.append((cedear_ticker, underlying, ratio_val))

        return results

    try:
        ratios = await asyncio.to_thread(_parse, pdf_content)
        return RatioFetchResult(ratios, source_date)
    except Exception:
        logger.exception("Failed to parse BYMA CEDEAR PDF.")
        return RatioFetchResult([], source_date)


# --- FCI (mutual fund) price provider ---

CAFCI_EXCEL_URL = "https://api.pub.cafci.org.ar/pb_get"
CAFCI_TIMEOUT = 30.0
CAFCI_HEADER_SCAN_MAX_ROW = 15
CAFCI_CODE_HEADER = "código cafci"
CAFCI_VCP_HEADER = "valor"
CAFCI_DATE_HEADER = "fecha"
CAFCI_CURRENCY_HEADER = "moneda fondo"

SOURCE_ARGENTIADATOS = "argentinadatos"
ARGENTIADATOS_BASE = "https://api.argentinadatos.com/v1/finanzas/fci"
ARGENTIADATOS_TYPES = ["mercadoDinero", "rentaFija", "rentaVariable", "rentaMixta", "otros"]
ARGENTIADATOS_TIMEOUT = 15.0

# Module-level caches. Populated on first fetch per process lifecycle.
# _cafci_prices: code → (date, price, currency). All funds from the latest Excel download.
# _cafci_registry: code → fund name. Used for ArgentinaDatos fallback.
_cafci_prices: dict[str, tuple[date_type, Decimal, str]] | None = None
# Whether this cycle's CAFCI download or parse failed. A failure leaves _cafci_prices as an EMPTY DICT
# rather than None so a second caller does not re-download — good, but that one sentinel then has to
# mean two different things, and the chain needs them apart: an empty dict because CAFCI is down must
# fall through to ArgentinaDatos, while an empty result for a fund CAFCI simply does not list must not.
# Without this flag a CAFCI outage reads as "this fund has no price" and silently skips the fallback.
_cafci_load_failed = False
_cafci_registry: dict[str, str] | None = None
_cafci_lock: asyncio.Lock | None = None


# Returns the process-wide CAFCI download lock, creating it lazily on first use.
def _get_cafci_lock() -> asyncio.Lock:
    global _cafci_lock
    if _cafci_lock is None:
        _cafci_lock = asyncio.Lock()
    return _cafci_lock


# Clears the CAFCI cache. Called before each refresh cycle so the next fetch re-downloads.
def clear_fci_cache() -> None:
    global _cafci_prices, _cafci_registry, _cafci_load_failed
    _cafci_prices = None
    _cafci_registry = None
    _cafci_load_failed = False


# Fetches the latest FCI cuotaparte price for a given CAFCI code, from the CAFCI public Excel.
#
# Its ArgentinaDatos fallback used to live INSIDE this function, and moving it out to a chain entry of
# its own is what stops the stored source lying: every price served by the fallback was written with
# source "cafci", because the row's source came from the category map rather than from whoever actually
# answered. SOURCE_ARGENTIADATOS was declared and never once used.
async def fetch_cafci(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    # Try cached CAFCI data first (populated by the first call in the refresh cycle).
    if _cafci_load_failed:
        raise PriceProviderUnavailable(f"CAFCI Excel unavailable for {ticker}.")
    if _cafci_prices is not None:
        entry = _cafci_prices.get(ticker)
        return [entry] if entry else []

    # First call — download and cache. Lock ensures only one download even with concurrent calls.
    async with _get_cafci_lock():
        # Re-check after acquiring lock (another coroutine may have populated the cache, or already
        # found the service down — in which case this ticker must report that rather than re-download).
        if _cafci_load_failed:
            raise PriceProviderUnavailable(f"CAFCI Excel unavailable for {ticker}.")
        if _cafci_prices is not None:
            entry = _cafci_prices.get(ticker)
            return [entry] if entry else []
        await _load_cafci_cache()

    # The download or parse failing is the provider not ANSWERING, and it has to say so: the loader
    # leaves an empty dict behind either way, so reading the dict alone would report a CAFCI outage as
    # "this fund has no price" and stop the chain before ArgentinaDatos.
    if _cafci_load_failed or _cafci_prices is None:
        raise PriceProviderUnavailable(f"CAFCI Excel unavailable for {ticker}.")

    entry = _cafci_prices.get(ticker)
    return [entry] if entry else []


# Fetches an FCI price from the ArgentinaDatos JSON API, the fallback behind CAFCI.
#
# Worth knowing before relying on it: it resolves a fund by NAME, and the name comes from the registry
# that _load_cafci_cache builds — so it covers "CAFCI answered but does not carry this fund" and not
# "CAFCI is down", where the registry is empty and there is no name to search by. That was equally true
# when the fallback was nested inside fetch_cafci; it is only visible now.
async def fetch_argentinadatos(
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> PriceResult:
    return await _fetch_fci_from_argentinadatos(ticker)


# Downloads the CAFCI Excel and caches all fund prices + registry in module-level dicts.
# Called once per refresh cycle — subsequent fetch_cafci() calls read from cache.
async def _load_cafci_cache() -> None:
    global _cafci_prices, _cafci_registry, _cafci_load_failed
    import asyncio
    import io

    try:
        async with httpx.AsyncClient(timeout=CAFCI_TIMEOUT) as client:
            response = await client.get(CAFCI_EXCEL_URL)
            response.raise_for_status()
            content = response.content
    except httpx.HTTPError:
        logger.exception("CAFCI Excel fetch failed.")
        _cafci_prices = {}
        _cafci_load_failed = True
        return

    def _parse(data: bytes) -> tuple[dict[str, tuple[date_type, Decimal, str]], dict[str, str]]:
        import re

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return {}, {}

        # Find the header row by locating the CAFCI code column, then map all columns from that row.
        code_col = None
        vcp_col = None
        date_col = None
        currency_col = None
        header_row = None

        for row in ws.iter_rows(min_row=1, max_row=CAFCI_HEADER_SCAN_MAX_ROW, values_only=False):
            for cell in row:
                if CAFCI_CODE_HEADER in str(cell.value or "").strip().lower():
                    header_row = cell.row
                    break
            if header_row:
                for cell in row:
                    val = str(cell.value or "").strip().lower()
                    if CAFCI_CODE_HEADER in val:
                        code_col = cell.column
                    if CAFCI_VCP_HEADER in val:
                        vcp_col = cell.column
                    if CAFCI_DATE_HEADER in val:
                        date_col = cell.column
                    if CAFCI_CURRENCY_HEADER in val:
                        currency_col = cell.column
                break

        if not header_row or not code_col or not vcp_col:
            logger.warning("Could not find header columns in CAFCI Excel.")
            wb.close()
            return {}, {}

        # Parse all rows into the prices dict and registry.
        prices: dict[str, tuple[date_type, Decimal, str]] = {}
        registry: dict[str, str] = {}

        for row in ws.iter_rows(min_row=header_row + 2, values_only=False):
            code_cell = row[code_col - 1].value if len(row) >= code_col else None
            if not code_cell:
                continue

            code_str = str(int(code_cell)) if isinstance(code_cell, (int, float)) else str(code_cell).strip()
            fund_name = str(row[0].value or "").strip()
            if fund_name:
                registry[code_str] = fund_name

            # Extract VCP.
            vcp_cell = row[vcp_col - 1].value if len(row) >= vcp_col else None
            if not vcp_cell:
                continue
            try:
                vcp = Decimal(str(vcp_cell).strip().replace(",", "."))
            except Exception:
                continue
            if vcp <= 0:
                continue

            # Extract date.
            price_date = None
            if date_col:
                date_cell = row[date_col - 1].value if len(row) >= date_col else None
                if isinstance(date_cell, date_type):
                    price_date = date_cell
                elif date_cell:
                    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", str(date_cell))
                    if match:
                        y = int(match.group(3))
                        if y < 100:
                            y += 2000
                        try:
                            price_date = date_type(y, int(match.group(2)), int(match.group(1)))
                        except ValueError:
                            pass

            if not price_date:
                price_date = date_type.today()

            # Extract currency.
            currency = "ARS"
            if currency_col:
                curr_cell = row[currency_col - 1].value if len(row) >= currency_col else None
                if curr_cell:
                    currency = str(curr_cell).strip().upper()

            prices[code_str] = (price_date, vcp, currency)

        wb.close()
        return prices, registry

    try:
        prices, registry = await asyncio.to_thread(_parse, content)
        _cafci_prices = prices
        _cafci_registry = registry
        logger.info("CAFCI cache loaded: %d prices, %d registry entries.", len(prices), len(registry))
    except Exception:
        logger.exception("Failed to parse CAFCI Excel.")
        _cafci_prices = {}
        _cafci_load_failed = True


# Fetches FCI price from the ArgentinaDatos JSON API (fallback).
# Requires _cafci_registry to map CAFCI code → fund name.
async def _fetch_fci_from_argentinadatos(ticker: str) -> PriceResult:
    global _cafci_registry

    # Need the fund name to search in ArgentinaDatos.
    fund_name = (_cafci_registry or {}).get(ticker)
    if not fund_name:
        logger.warning("No fund name in registry for CAFCI code %s. Cannot query ArgentinaDatos.", ticker)
        return []

    # Fetch all types in parallel.
    async def _fetch_type(fci_type: str) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=ARGENTIADATOS_TIMEOUT) as client:
                response = await client.get(f"{ARGENTIADATOS_BASE}/{fci_type}/ultimo")
                response.raise_for_status()
                return response.json()
        except Exception:
            return []

    import asyncio

    all_results = await asyncio.gather(*[_fetch_type(t) for t in ARGENTIADATOS_TYPES])

    # Search all responses for the fund name.
    fund_name_lower = fund_name.lower()
    for items in all_results:
        for item in items:
            fondo = (item.get("fondo") or "").strip()
            if fondo.lower() == fund_name_lower:
                vcp = item.get("vcp")
                fecha = item.get("fecha")
                if not vcp or not fecha:
                    continue
                try:
                    price_date = date_type.fromisoformat(fecha)
                    price_val = Decimal(str(vcp))
                    return [(price_date, price_val, "ARS")]
                except Exception:
                    continue

    logger.warning("Fund '%s' not found in ArgentinaDatos.", fund_name)
    return []
