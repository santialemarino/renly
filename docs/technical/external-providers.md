# External Data Providers in Renly

All external data fetching follows a standardized provider pattern. This applies to both asset price providers and exchange rate providers.

## Pattern

Each provider is a **stateless async function** with a uniform signature and return type. The service layer maps categories (or a flat list) to providers and handles storage — it never contains provider-specific logic (URLs, response parsing, field mapping).

### Structure

```
providers file       → fetch functions + ProviderInfo registry
service file         → maps categories to providers, iterates and stores
```

To swap a provider, change one line in the mapping. To add a provider, write a fetch function and add it to the registry.

### Price providers (`services/price_providers.py`)

**Signature:**

```python
async def fetch_<name>(ticker: str, start_date: date | None = None, end_date: date | None = None) -> PriceResult
```

Where `PriceResult = list[tuple[date, Decimal, str]]` (date, price, currency). Providers that don't support date ranges accept the parameters but ignore them.

A provider reports its two outcomes **separately**, and the fallback chain rests entirely on that
distinction:

- **returns a list** (empty included) — the provider answered. An empty list means the ticker genuinely
  has no price for that range: a weekend, a delisting, a symbol the provider does not carry.
- **raises `PriceProviderUnavailable`** — the provider could not answer: an HTTP error, a rate limit, an
  unparseable payload, a missing credential.

Only the second advances the chain. Returning `[]` for both, as every provider originally did, makes a
throttled API indistinguishable from a quiet market — so a chain built on it would walk every provider
every weekend and still could not report an outage.

**Registry** (in `asset_price_service.py`) — an ordered chain per category, primary first:

```python
_CATEGORY_PROVIDERS: dict[InvestmentCategory, tuple[PriceProviderInfo, ...]] = {
    InvestmentCategory.stocks:           (_YFINANCE, _FINNHUB),
    InvestmentCategory.cedears:          (_YFINANCE, _DATA912),
    InvestmentCategory.government_bonds: (_YFINANCE, _DATA912),
    InvestmentCategory.crypto:           (coingecko, coinbase),
    InvestmentCategory.fci:              (cafci, argentinadatos),
}
```

**Metadata:** `PriceProviderInfo(source, fetch, supports_history, is_configured)` — NamedTuple.
`is_configured` lets a provider needing an unset credential be _skipped_ rather than counted as a
failure. Note a `PriceProviderInfo` is itself a tuple, so a chain must be written `(provider,)` — a bare
`provider` iterates its fields.

The chain skips a provider that cannot answer the question asked: one with `supports_history=False` is
never called for a dated lookup, because a live quote answered to "what did this cost in January" is a
wrong answer rather than a missing one.

**The stored `source` is whichever provider actually served the row**, not the category's primary. This
is why the source travels back with the result: reading it from the registry meant every FCI price
served by the ArgentinaDatos fallback was written down as `cafci`.

When every provider in a chain fails, the service logs an **error** naming the ticker, and the refresh
logs one line listing every ticker left unpriced. Prices simply stop updating otherwise — the app keeps
rendering the last stored value with nothing saying so.

**Cached providers remember that they failed.** CAFCI and data912 each download one snapshot per refresh
cycle, and a failed load has to be recorded as a failure rather than as an empty snapshot — a single
"cache is empty" sentinel cannot say whether the service is down or simply does not list that ticker,
and the chain needs those apart. Getting it wrong breaks in both directions, and both were real:
data912 without the flag re-downloaded per ticker (measured at 60 requests to a service already
answering 502, for 20 tickers), while CAFCI's existing empty-dict sentinel reported an outage as "this
fund has no price", which is an _answer_ — so the chain stopped and ArgentinaDatos was never reached on
the one outage it exists for. The flag lives for the cycle and `clear_*_cache()` resets it alongside the
data.

### Exchange rate providers (`services/exchange_rate_providers.py`)

**Signature:**

```python
async def fetch_<name>() -> ExchangeRateResult
```

Where `ExchangeRateResult = list[tuple[ExchangeRatePair, Decimal]]`. Each provider returns `(pair, rate)` tuples. The service iterates `EXCHANGE_RATE_PROVIDERS` and stores results.

**Registry** (in `exchange_rate_providers.py`):

```python
EXCHANGE_RATE_PROVIDERS = [
    ExchangeRateProviderInfo("dolarapi", fetch_dolarapi),
    ExchangeRateProviderInfo("frankfurter", fetch_frankfurter),
]
```

**Metadata:** `ExchangeRateProviderInfo(source, fetch)` — NamedTuple.

### Frontend category capabilities (`lib/constants/categories.ts`)

The frontend mirrors provider capabilities for UI decisions:

```typescript
CATEGORY_CAPABILITIES: Record<InvestmentCategory, CategoryCapability> = {
  stocks: { hasTicker: true, hasAutoPrice: true, supportsHistory: true },
  crypto: { hasTicker: true, hasAutoPrice: true, supportsHistory: false },
  corporate_bonds: { hasTicker: false, hasAutoPrice: false, supportsHistory: false },
  // ...
};
```

Used by the investment form to show/hide the ticker field and display category-specific ticker hints.

## Current providers

### Price providers

| Provider       | Role     | Categories                        | History          | Key | Notes                                                                                                                       |
| -------------- | -------- | --------------------------------- | ---------------- | --- | --------------------------------------------------------------------------------------------------------------------------- |
| yfinance       | primary  | stocks, cedears, government_bonds | Yes              | No  | `.BA` suffix for Argentine assets. Scrapes an endpoint it does not own, so it breaks independently of Yahoo.                |
| Finnhub        | fallback | stocks                            | No (quote only)  | Yes | `FINNHUB_API_KEY`, free tier 60/min. The only price source independent of Yahoo. Unset = dropped from the chain.            |
| data912        | fallback | cedears, government_bonds         | No (live board)  | No  | One call returns every BYMA symbol; cached per refresh cycle. Renly's `.BA` suffix is stripped for the lookup. Prices ARS.  |
| CoinGecko      | primary  | crypto                            | No (last 7 days) | No  | Addressed by coin id. Reports a rate limit as **HTTP 200 with the error in the body** — read the body, not the status.      |
| Coinbase       | fallback | crypto                            | Yes (dated spot) | No  | Addressed by symbol. Far more headroom than CoinGecko's free tier. 404 = asset not listed, which is an answer.              |
| CAFCI          | primary  | fci                               | No (daily only)  | No  | Public xlsx at `api.pub.cafci.org.ar/pb_get`. Ticker = CAFCI code (e.g., 2409). Direct row lookup.                          |
| ArgentinaDatos | fallback | fci                               | No (daily only)  | No  | Resolves a fund by NAME from the registry CAFCI's download builds — so it covers "CAFCI lacks this fund", not "CAFCI down". |

**Crypto tickers:** the two crypto providers disagree about what a ticker is — CoinGecko wants the coin
id (`bitcoin`), Coinbase the symbol (`BTC`) — and nothing validates it on entry, so both spellings exist
in stored data. Each provider translates the stored ticker into its own vocabulary
(`to_coingecko_id` / `to_crypto_symbol`), with an unlisted ticker passing through unchanged.

**Why not Yahoo's chart endpoint as a second equity leg:** it was built and then removed on measurement.
Called directly it answers `429` for a given host while yfinance — which negotiates a cookie and crumb
first — succeeds against the same upstream in the same second. A fallback that fails whenever it is
reached costs a round trip and reports an outage that is its own.

### CEDEAR ratio providers

| Provider | Format | Notes                                                                                             |
| -------- | ------ | ------------------------------------------------------------------------------------------------- |
| Comafi   | Excel  | Primary. Principal CEDEAR issuer (90%+ programs). Fixed URL. ~306 ratios.                         |
| BYMA     | PDF    | Fallback. Dynamic URL (date in filename, scraped from page). ~401 ratios. Parsed with pdfplumber. |

The service fetches both in parallel (`asyncio.gather`). Selection: newer source date wins → more entries breaks ties → Comafi preferred if still tied.

### Exchange rate providers

| Provider    | Pairs                      | Notes                 |
| ----------- | -------------------------- | --------------------- |
| DolarApi    | USD/ARS oficial, MEP, blue | Averages compra/venta |
| Frankfurter | USD/BRL, USD/EUR, USD/GBP  | ECB data              |

## Adding a new provider

1. Create the fetch function in the appropriate providers file.
2. Follow the uniform signature — return the standard result type, and raise `PriceProviderUnavailable`
   (rather than returning `[]`) for anything that means the provider could not answer.
3. Add it to the mapping (`_CATEGORY_PROVIDERS` or `EXCHANGE_RATE_PROVIDERS`). For prices that means a
   position in the category's chain; set `supports_history` honestly and give it an `is_configured` if
   it needs a credential.
4. Declare its source as a `SOURCE_*` constant — a chain may only store sources that exist as one.
5. Update `CATEGORY_CAPABILITIES` in the frontend if it affects a category.
6. No service or router changes needed.

## Transactional email (SHELL-3)

Account-lifecycle emails (verification, password reset, "you already have an account", email-change
confirmation) go through the same port-and-adapter shape, in `services/email_service.py`:

- **`EmailService`** — the port (abstract `send(EmailMessage)`).
- **`ConsoleEmailService`** — logs the message to the API logs. Default for local dev / tests, so
  the verification/reset links are visible without a real provider.
- **`ResendEmailService`** — sends via the Resend HTTP API (`POST https://api.resend.com/emails`).
- **`get_email_service()`** — the selector: returns the adapter for `EMAIL_PROVIDER` (`console` |
  `resend`), cached. Resend requires `EMAIL_API_KEY` (validated at startup) and `EMAIL_FROM`.

Message bodies are built by pure functions in `services/email_templates.py` (one per email type),
each returning an `EmailMessage`. To swap providers, add an adapter and one branch in the selector;
no caller changes. Emails are sent best-effort after the DB transaction commits (`auth_service._safe_send`),
so a provider outage never blocks or de-uniforms the request — the user can re-request the email.
