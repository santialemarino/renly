# Asset Price Handling in Renly

## User-facing behaviour

Investments with a `ticker` field get automatic price fetching. The ticker determines the data source based on the investment's category:

| Category  | Source    | Ticker format               | Price currency |
| --------- | --------- | --------------------------- | -------------- |
| `stocks`  | yfinance  | US symbols (AAPL, MSFT)     | USD            |
| `cedears` | yfinance  | .BA suffix (AAPL.BA)        | ARS            |
| `crypto`  | CoinGecko | coin id (bitcoin, ethereum) | USD            |
| `fci`     | TBD       | fund code                   | ARS            |
| `bonds`   | TBD       | ISIN                        | —              |

Investments without a ticker function as manual-entry — the user enters snapshot values directly.

## Architecture

### 1. Price providers

Price providers are stateless functions in `services/price_providers.py`. Each returns a list of `(date, price, currency)` tuples. The service layer handles storage.

**yfinance** (stocks + CEDEARs):

- Python library that wraps Yahoo Finance data.
- Supports `.BA` tickers for Argentine CEDEARs (returns ARS prices).
- Fetches daily closing prices. Default period: last 5 days; supports custom date ranges.
- Runs in a thread pool (`asyncio.to_thread`) since yfinance is synchronous.
- No API key required. Rate limits are informal (Yahoo can throttle aggressive scraping).

**CoinGecko** (crypto):

- REST API at `api.coingecko.com/api/v3`.
- Uses coin ids (e.g. `bitcoin`, `ethereum`), not ticker symbols.
- `/coins/{id}/market_chart` for historical daily prices.
- `/simple/price` for current price.
- No API key required (Demo plan: ~30 req/min).

### 2. Source resolver

The service layer (`services/asset_price_service.py`) maps investment categories to providers:

```
category == stocks or cedears → yfinance
category == crypto → CoinGecko
other categories → no provider (manual entry)
```

The router calls `fetch_and_store_prices(session, ticker, category)` and the service selects the right provider. Results are stored in `asset_prices` uniformly regardless of source.

### 3. CEDEAR ratios

CEDEAR ratios define how many CEDEARs equal one underlying share (e.g. 10 AAPL.BA = 1 AAPL). They are separate from prices — a CEDEAR has both a price (in ARS) and a ratio (structural conversion factor).

**Source:** Banco Comafi Excel file at `comafi.com.ar/Multimedios/otros/7279.xlsx`. Comafi is the depositary institution that issues CEDEARs — this is the authoritative source for all ~338 programs.

**Fetching:** The `fetch_comafi_ratios()` provider downloads the Excel file, parses headers dynamically to locate the ticker and ratio columns, and extracts all entries. The ratio format varies (`"10:1"`, `"10"`, `"10.0"`) — the parser handles all formats.

**Storage:** Each ratio is stored in `cedear_ratios` keyed by `(ticker, effective_date)`. Multiple rows per ticker allow tracking historical ratio changes (e.g. after a stock split).

### 4. Scheduled jobs

| Job            | Frequency                         | Trigger    | What it does                                                            |
| -------------- | --------------------------------- | ---------- | ----------------------------------------------------------------------- |
| Exchange rates | Every 6 hours + startup           | `interval` | DolarApi + Frankfurter → `exchange_rates`                               |
| Asset prices   | Weekly (Sun 20:00 UTC)            | `cron`     | yfinance + CoinGecko → `asset_prices` for all ticker-linked investments |
| CEDEAR ratios  | Monthly (1st 12:00 UTC) + startup | `cron`     | Comafi Excel → `cedear_ratios` for all ~338 programs                    |

The asset prices job iterates all active investments with a ticker set, calls the appropriate provider for each, and stores results. If a provider fails for one ticker, that investment is skipped (not the entire job).

### 5. API endpoints

| Endpoint                        | Method | Description                                                            |
| ------------------------------- | ------ | ---------------------------------------------------------------------- |
| `/asset-prices/{ticker}/latest` | GET    | Latest stored price for a ticker                                       |
| `/asset-prices/{ticker}`        | GET    | Price history with optional `start_date`/`end_date` query params       |
| `/asset-prices/refresh`         | POST   | Triggers on-demand price fetch for all ticker-linked investments (202) |

All endpoints require authentication.

## Data model

```sql
-- One row per ticker per date. Source tracks the provider.
asset_prices (ticker, date, price, currency, source)
  UNIQUE (ticker, date)

-- One row per CEDEAR per effective_date. Tracks ratio changes over time.
cedear_ratios (ticker, underlying, ratio, effective_date, source)
  UNIQUE (ticker, effective_date)
```

The `source` field values: `yfinance`, `coingecko`, `comafi`, `manual`.

## Failure handling

- **yfinance unavailable:** The investment is skipped in the scheduled job. A warning is logged. The investment functions as manual-entry until the next successful fetch.
- **CoinGecko unavailable:** Same — skip and log.
- **Comafi Excel unavailable:** CEDEAR ratios are not updated. Existing ratios in the DB remain valid (ratios change only on stock splits, which are rare).
- **Ticker not found:** yfinance returns an empty DataFrame; CoinGecko returns an empty response. The service stores 0 prices and moves on. No error is raised.

## Pending

- **FCI prices:** CAFCI API integration for mutual fund NAVs (undocumented but stable endpoints at `api.cafci.org.ar`).
- **Auto-snapshots:** Weekly job that uses the latest price + last known quantity to auto-generate snapshots with `source: 'auto'` (PR 4).
- **Historical price lookup:** When creating a past snapshot, fetch the historical price for that date to pre-fill the form (PR 5).
- **Value ↔ quantity derivation:** Auto-calculate one from the other using the fetched price (PR 5).
