# Currency Handling in Renly

## User-facing behaviour

The global currency switcher in the sidebar offers three options (configured in Settings):

| Option                            | What the user sees                                                                                                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Primary currency** (e.g. ARS)   | All values converted to ARS                                                                                                                                                                |
| **Secondary currency** (e.g. USD) | All values converted to USD. For USD, three variants are available: USD (oficial), USD MEP, USD Blue — each uses a different exchange rate.                                                |
| **Original (X)**                  | Per-investment pages show each investment in its `base_currency`. The dashboard falls back to the primary currency (since aggregated metrics can't sum mixed currencies) and shows a hint. |

### Supported conversion pairs

Only **ARS ↔ USD** conversion is currently supported (via DolarApi — oficial, MEP, blue rates). USD appears as three selectable variants in the currency combobox: **USD (Official)** uses the oficial rate, **USD (MEP)** uses the MEP/bolsa rate, and **USD (Blue)** uses the blue/parallel rate. Other ISO 4217 currencies can be configured in Settings but will display a warning icon and toast. Values fall back to original currency when conversion is not available.

## Architecture

### 1. Currency selection (frontend)

```
User clicks switcher → Zustand store updates → Cookie persisted (active-currency, 1yr)
                       → router.refresh() triggers server component re-render
```

- **Store**: `lib/stores/currency-store.ts` — Zustand with `activeCurrency` state.
- **Cookie**: `ACTIVE_CURRENCY_COOKIE = 'active-currency'` — read by server components.
- **Switcher**: `_components/currency-switcher.tsx` — ToggleGroup of `displayCurrencies`.
- **Layout**: `(protected)/layout.tsx` — reads Settings API for primary/secondary, resolves `displayCurrencies` array, reads cookie for active selection.

### 2. Server component data flow

Each page reads the cookie and passes `currency` to API functions:

```
page.tsx → cookies().get('active-currency') → 'USD' | 'ARS' | 'original'
         → if 'original': pass undefined (no conversion) or fall back to primary (dashboard)
         → if currency: pass to API as ?currency=USD
```

- **Snapshots page**: passes `currency` to `getSnapshotGrid({ currency })`.
- **Dashboard page**: passes `currency` to all 5 metric endpoints. When "Original" is selected, falls back to the user's primary currency from Settings (aggregated metrics require a common currency).

### 3. Backend conversion

All conversion happens at query time in the service layer. Stored values are never modified.

```
Service function receives currency param (e.g. "USD", "USD_MEP", "USD_BLUE")
  → mh.get_conversion_rate(session, currency) resolves the right USD/ARS pair
  → mh.convert_value(value, from_currency, to_currency, rate)
     → USD → ARS: value × rate
     → ARS → USD: value ÷ rate
     → Same currency or unsupported pair: return unchanged
```

- **Helpers**: `services/metrics_helpers.py` — `convert_value()`, `get_conversion_rate()`.
- **Domain**: `domain/currency.py` — `parse_currency()` maps virtual codes to `(base_currency, ExchangeRatePair)`.
- **Rate resolution**: `get_conversion_rate()` is centralized in `metrics_helpers.py`. It parses the currency code to determine which rate pair to use (USD → oficial, USD_MEP → MEP, USD_BLUE → blue), with fallback to oficial if the preferred pair is unavailable.
- **Schema fields**: All monetary API responses include a `currency` field indicating the display currency.

### 4. Original values for editing

The snapshot grid returns both converted and original values:

| Field                         | Purpose                                                    |
| ----------------------------- | ---------------------------------------------------------- |
| `value`                       | Display value (converted if currency requested)            |
| `original_value`              | Base currency value (always unconverted, for form editing) |
| `transaction.amount`          | Display amount (converted)                                 |
| `transaction.original_amount` | Base currency amount (for form editing)                    |

The snapshot form always uses `original_value` / `original_amount` to populate fields, ensuring edits are saved in the investment's `base_currency` regardless of the display currency.

### 5. Exchange rate fetching

Rates are fetched from [DolarApi](https://dolarapi.com) on a schedule:

- **On startup**: immediate fetch (`next_run_time=datetime.now()`).
- **Every 6 hours**: APScheduler cron job.
- **Endpoint**: `GET https://dolarapi.com/v1/dolares` — returns oficial, blue, MEP rates.
- **Storage**: `exchange_rates` table with unique constraint on `(date, pair)`. Upsert on each fetch.
- **Pairs**: `USD_ARS_OFICIAL`, `USD_ARS_MEP`, `USD_ARS_BLUE` (enum `ExchangeRatePair`).
- **Rate value**: average of buy and sell prices from the API response.

### 6. Settings form — currency configuration

The Settings page (`/settings`) lets the user configure primary and secondary currencies:

- **Primary currency**: required. The default display currency (shown first in the switcher, used as fallback when "Original" is selected on the dashboard).
- **Secondary currency**: optional. Shown as the second option in the sidebar switcher.

Both fields use a `CurrencyCombobox` with flag emoji, ranked search, and the full ISO 4217 allowlist. USD appears as three variants (Official, MEP, Blue) in a separate group at the top of the combobox, each with a badge tag. The backend stores the selected code (e.g. `USD`, `USD_MEP`, `USD_BLUE`) in `user_settings` (fields: `primary_currency`, `secondary_currency`) via `PUT /settings`.

**How the switcher options are built** (in `(protected)/layout.tsx`):

1. Load settings from API → `primary` and `secondary`.
2. Build `displayCurrencies = [primary, secondary?, 'original']`.
3. Read `active-currency` cookie → if the saved value isn't in `displayCurrencies`, default to `primary`.
4. Pass `displayCurrencies` and `activeCurrency` to the sidebar switcher.

If no settings exist yet (first login), fallback env vars are used: `NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY` (default `ARS`) and `NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY` (default `USD`).

### 7. Unsupported currency warnings (§11.4.1)

Only USD and ARS have exchange rate support. When a user selects any other currency, warnings appear at three points:

**Settings form (passive + on selection):**

- An animated `AlertTriangle` icon (amber, scale animation) appears next to the label of each combobox when its selected currency is unsupported.
- When either currency is unsupported, a `WarningHint` block appears below both comboboxes (separated by a `Separator`) with the text: _"Currencies that don't have exchange rate support yet. Conversion will be available soon."_
- On selection of an unsupported currency, a **warning toast** (amber) is shown: _"Exchange rate conversion for {CURRENCY} is not available yet. Values will be shown in their original currency."_

**Currency switcher (on switch):**

- When the user switches to an unsupported currency via the sidebar, a **warning toast** (amber) is shown: _"Conversion to {CURRENCY} is not available yet. Showing values in original currency."_

**Fallback behaviour:**

- When conversion is not possible, all monetary values fall back to their `base_currency` (same as "Original" mode). No error — the page renders normally, just without conversion.

**Supported check:** `lib/utils/currency.ts` — `isCurrencySupported()` checks against `['USD', 'USD_MEP', 'USD_BLUE', 'ARS']`.

### 8. Unconvertible investments in metrics

When the dashboard requests metrics in a specific currency (e.g. ARS), investments with a base currency that can't be converted (e.g. EUR) are **excluded** from all aggregated metrics to avoid silently summing mixed currencies.

**Backend flow:**

1. `can_convert(from, to)` in `metrics_helpers.py` checks if the pair is supported (same currency or USD↔ARS).
2. `_split_by_convertibility()` in `metrics_service.py` splits investments into convertible and skipped lists.
3. Only convertible investments are used for computation. Skipped investments are returned in `skipped_investments` on every response.
4. If conversion is needed but no exchange rates exist in the DB, `ExchangeRateUnavailableError` (503) is raised.

**Frontend handling:**

- The dashboard shows a `WarningHint` listing skipped investments: _"Some investments were excluded because their currency can't be converted: Name (EUR)."_
- If the API returns 503 (no rates at all), the dashboard shows a generic error fallback: _"Unable to load dashboard data."_

### 9. Edge cases summary

| Scenario                         | Behaviour                                           |
| -------------------------------- | --------------------------------------------------- |
| All investments USD, display ARS | All converted via MEP rate                          |
| Mixed USD+ARS, display ARS       | Both converted correctly                            |
| EUR investment, display ARS      | EUR investment excluded, warning shown              |
| Display currency EUR             | USD and ARS investments excluded, warning lists all |
| All investments same as display  | No conversion needed, no rate fetched               |
| No exchange rates in DB          | 503 error, dashboard shows load error fallback      |
| "Original" selected on dashboard | Falls back to primary currency, hint shown          |
| "Original" on snapshots page     | No conversion, values in base currency              |

## Data model

```sql
-- Each investment has a base currency
investments.base_currency  -- e.g. 'USD', 'ARS'

-- Snapshots and transactions store values in the investment's base currency
investment_snapshots.value     -- always in base_currency
investment_snapshots.currency  -- same as investment.base_currency
transactions.amount            -- always in base_currency
transactions.currency          -- same as investment.base_currency

-- Exchange rates fetched from DolarApi
exchange_rates.pair   -- USD_ARS_OFICIAL | USD_ARS_MEP | USD_ARS_BLUE
exchange_rates.rate   -- e.g. 1250.50 (1 USD = 1250.50 ARS)
exchange_rates.date   -- rate date
```

## USD variant system

USD appears as three virtual currency codes, each mapped to a different exchange rate:

| Code       | Label             | Rate pair         |
| ---------- | ----------------- | ----------------- |
| `USD`      | Dollar (Official) | `USD_ARS_OFICIAL` |
| `USD_MEP`  | Dollar (MEP)      | `USD_ARS_MEP`     |
| `USD_BLUE` | Dollar (Blue)     | `USD_ARS_BLUE`    |

**Backend:** `domain/currency.py` defines `parse_currency()` which maps a virtual code to `(base_currency, ExchangeRatePair)`. `metrics_helpers.get_conversion_rate()` uses this to pick the right rate. `can_convert()` and `convert_value()` resolve variants to base `"USD"` via `base_currency()`.

**Frontend:** Variants are defined in `lib/constants/currency.ts` (`USD_VARIANTS`). The `CurrencyCombobox` shows them as a grouped section at the top with badge tags. The sidebar `PillToggleGroup` shows short labels (USD, USD M, USD B). `lib/utils/currency.ts` provides `isUsdVariant()`, `baseCurrency()`, and `isCurrencySupported()`.

## Future: additional rate sources

To support currencies beyond ARS/USD:

1. Add a new rate source (e.g. European Central Bank for EUR, Open Exchange Rates for broad coverage).
2. Add new `ExchangeRatePair` enum values.
3. Extend `convert_value()` to handle multi-hop conversions (e.g. EUR → USD → ARS).
4. Update `isCurrencySupported()` to include the new currencies.
5. Remove the warning icons/toasts for the newly supported currencies.
