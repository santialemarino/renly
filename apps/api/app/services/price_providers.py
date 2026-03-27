# Price provider implementations for fetching asset prices from external APIs.
# Each provider returns a list of (date, price, currency) tuples.
# Providers are stateless — they fetch and return, the service handles storage.

import logging
from datetime import date as date_type
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

# Source name constants (stored in the source column of asset_prices/cedear_ratios).
SOURCE_YFINANCE = "yfinance"
SOURCE_COINGECKO = "coingecko"

PriceResult = list[tuple[date_type, Decimal, str]]


# Fetches prices from Yahoo Finance via yfinance for stocks and CEDEARs.
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
            kwargs["end"] = end_date.isoformat()
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
    except Exception:
        logger.exception("yfinance fetch failed for %s.", ticker)
        return []


# Fetches prices from CoinGecko for crypto assets.
# ticker should be a CoinGecko coin id (e.g. "bitcoin", "ethereum").
async def fetch_coingecko(
    ticker: str,
    vs_currency: str = "usd",
) -> PriceResult:
    url = f"https://api.coingecko.com/api/v3/coins/{ticker}/market_chart"
    params = {"vs_currency": vs_currency, "days": "7", "interval": "daily"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        logger.exception("CoinGecko fetch failed for %s.", ticker)
        return []

    prices = data.get("prices", [])
    results: PriceResult = []
    currency = vs_currency.upper()
    for timestamp_ms, price in prices:
        price_date = date_type.fromtimestamp(timestamp_ms / 1000)
        results.append((price_date, Decimal(str(round(price, 6))), currency))
    return results


# Fetches current price from CoinGecko simple API for a single coin.
async def fetch_coingecko_current(
    ticker: str,
    vs_currency: str = "usd",
) -> tuple[Decimal, str] | None:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ticker, "vs_currencies": vs_currency}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        logger.exception("CoinGecko current price fetch failed for %s.", ticker)
        return None

    coin_data = data.get(ticker)
    if not coin_data:
        return None
    price = coin_data.get(vs_currency)
    if price is None:
        return None
    return Decimal(str(price)), vs_currency.upper()


# CEDEAR ratio result: (ticker, underlying, ratio).
RatioResult = list[tuple[str, str, Decimal]]

# Banco Comafi Excel configuration.
COMAFI_CEDEAR_URL = "https://www.comafi.com.ar/Multimedios/otros/7279.xlsx"
COMAFI_TIMEOUT = 30.0
COMAFI_HEADER_SCAN_MAX_ROW = 15
COMAFI_TICKER_HEADER_KEYWORD = "mercado"
COMAFI_TICKER_HEADER_KEYWORD_2 = "identif"
COMAFI_RATIO_HEADER_KEYWORD = "ratio"
COMAFI_BYMA_SUFFIX = ".BA"
COMAFI_SOURCE = "comafi"
COMAFI_RATIO_SEPARATOR = ":"


# Fetches all CEDEAR ratios from Banco Comafi's Excel file.
# Returns a list of (cedear_ticker, underlying_ticker, ratio) tuples.
async def fetch_comafi_ratios() -> RatioResult:
    import asyncio
    import io

    try:
        async with httpx.AsyncClient(timeout=COMAFI_TIMEOUT) as client:
            response = await client.get(COMAFI_CEDEAR_URL)
            response.raise_for_status()
            content = response.content
    except httpx.HTTPError:
        logger.exception("Comafi CEDEAR Excel fetch failed.")
        return []

    def _parse(data: bytes) -> RatioResult:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return []

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
            return []

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
            cedear_ticker = (
                ticker_str if ticker_str.endswith(COMAFI_BYMA_SUFFIX) else f"{ticker_str}{COMAFI_BYMA_SUFFIX}"
            )
            # Underlying is the ticker without .BA.
            underlying = ticker_str.replace(COMAFI_BYMA_SUFFIX, "")

            results.append((cedear_ticker, underlying, ratio_val))

        wb.close()
        return results

    try:
        return await asyncio.to_thread(_parse, content)
    except Exception:
        logger.exception("Failed to parse Comafi CEDEAR Excel.")
        return []
