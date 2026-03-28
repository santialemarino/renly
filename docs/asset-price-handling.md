# Asset Price Handling in Renly

## User-facing behaviour

Investments with a `ticker` field get automatic price fetching. The ticker determines the data source based on the investment's category:

| Category           | Source    | Ticker format                 | Price currency |
| ------------------ | --------- | ----------------------------- | -------------- |
| `stocks`           | yfinance  | US symbols (AAPL, MSFT)       | USD            |
| `cedears`          | yfinance  | .BA suffix (AAPL.BA)          | ARS            |
| `crypto`           | CoinGecko | coin id (bitcoin, ethereum)   | USD            |
| `fci`              | TBD       | fund code                     | ARS            |
| `government_bonds` | yfinance  | .BA suffix (AL30.BA, GD30.BA) | ARS            |
| `corporate_bonds`  | Manual    | —                             | —              |

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
category == stocks or cedears or government_bonds → yfinance
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

| Job            | Frequency                                          | Trigger    | What it does                                                            |
| -------------- | -------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| Exchange rates | Every 6 hours + startup                            | `interval` | DolarApi + Frankfurter → `exchange_rates`                               |
| Asset prices   | Daily at 22:00 UTC (after market close)            | `cron`     | yfinance + CoinGecko → `asset_prices` for all ticker-linked investments |
| Auto-snapshots | Last day of month at 23:00 UTC (after price fetch) | `cron`     | Latest quantity × price → `investment_snapshots` with `source: 'auto'`  |
| CEDEAR ratios  | Monthly (1st 00:00 UTC) + startup                  | `cron`     | Comafi Excel → `cedear_ratios` for all ~338 programs                    |

All schedule constants are defined at the top of `scheduler.py`. The asset prices job iterates all active investments with a ticker set, calls the appropriate provider for each, and stores results. If a provider fails for one ticker, that investment is skipped (not the entire job).

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

### 6. Auto-snapshots

On the last day of each month (at 23:00 UTC, after the daily price fetch), the scheduler generates auto-snapshots for ticker-linked investments:

1. For each investment with a ticker: get the latest price from `asset_prices`.
2. Get the last known `quantity` from the most recent snapshot.
3. Compute `value = quantity × price` (or just the price if no quantity).
4. Create a snapshot with `source: 'auto'` for today's date.
5. Skip if a snapshot already exists for today (manual or auto).
6. Skip if no price data is available for the ticker.

The "Refresh prices" button in the snapshots toolbar triggers a price-only refresh on demand (`POST /asset-prices/refresh`) — it does not create auto-snapshots (those only come from the monthly scheduled job). Auto-generated snapshots can be edited like any other snapshot. The `source` field is stored but not displayed in the grid.

### 7. Historical price lookup

When the user picks a date in the snapshot form, the frontend calls `GET /asset-prices/{ticker}/lookup?date=DATE&category=CATEGORY`. The backend checks the DB first; if the price isn't stored, it fetches from the provider (yfinance/CoinGecko) and stores it before returning. This is a get-or-fetch pattern — the `asset_prices` table acts as a cache.

The form shows a loading state while fetching ("Fetching price..."), then displays the result ("Price: 195.50 USD") or "No price available." The price enables value ↔ quantity derivation.

### 8. Value ↔ quantity derivation

When the investment has a ticker and a price is available, a Switch toggle appears: "Enter as quantity." When enabled, the user types quantity (shares) and value auto-derives (`quantity × price`). When disabled (default), the user types value and quantity auto-derives (`value ÷ price`). The derived field is read-only with a formula hint.

For CEDEAR investments with a ratio, the form also shows the equivalent underlying shares (`quantity ÷ ratio`).

## Pending

- **FCI prices:** CAFCI API integration for mutual fund NAVs (undocumented but stable endpoints at `api.cafci.org.ar`).
