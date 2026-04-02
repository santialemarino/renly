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

**Registry** (in `asset_price_service.py`):

```python
_CATEGORY_PROVIDERS: dict[InvestmentCategory, PriceProviderInfo] = {
    InvestmentCategory.stocks:           PriceProviderInfo("yfinance", fetch_yfinance, supports_history=True),
    InvestmentCategory.cedears:          PriceProviderInfo("yfinance", fetch_yfinance, supports_history=True),
    InvestmentCategory.government_bonds: PriceProviderInfo("yfinance", fetch_yfinance, supports_history=True),
    InvestmentCategory.crypto:           PriceProviderInfo("coingecko", fetch_coingecko, supports_history=False),
}
```

**Metadata:** `PriceProviderInfo(source, fetch, supports_history)` — NamedTuple.

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

| Provider  | Categories                        | History          | Notes                                        |
| --------- | --------------------------------- | ---------------- | -------------------------------------------- |
| yfinance  | stocks, cedears, government_bonds | Yes              | `.BA` suffix for Argentine assets            |
| CoinGecko | crypto                            | No (last 7 days) | Uses coin ids, not tickers                   |
| CAFCI     | fci                               | Blocked          | API returns 401; FCI is manual-entry for now |

### Exchange rate providers

| Provider    | Pairs                      | Notes                 |
| ----------- | -------------------------- | --------------------- |
| DolarApi    | USD/ARS oficial, MEP, blue | Averages compra/venta |
| Frankfurter | USD/BRL, USD/EUR, USD/GBP  | ECB data              |

## Adding a new provider

1. Create the fetch function in the appropriate providers file.
2. Follow the uniform signature — return the standard result type.
3. Add it to the mapping (`_CATEGORY_PROVIDERS` or `EXCHANGE_RATE_PROVIDERS`).
4. Update `CATEGORY_CAPABILITIES` in the frontend if it affects a category.
5. No service or router changes needed.
