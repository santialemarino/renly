# Currency Handling in Renly

## User-facing behaviour

The global currency switcher in the sidebar offers three options (configured in Preferences):

| Option                            | What the user sees                                                                                                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Primary currency** (e.g. ARS)   | All values converted to ARS                                                                                                                                                                |
| **Secondary currency** (e.g. USD) | All values converted to USD                                                                                                                                                                |
| **Original (X)**                  | Per-investment pages show each investment in its `base_currency`. The dashboard falls back to the primary currency (since aggregated metrics can't sum mixed currencies) and shows a hint. |

### Supported currencies

Five currencies have exchange rate support: **USD**, **ARS**, **BRL**, **EUR**, **GBP**. Any pair converts through USD as pivot (see Multi-currency pivot conversion below). Other ISO 4217 currencies can be stored as an investment's `base_currency` but will display a warning icon and toast when selected in the currency combobox. Values fall back to original currency when conversion is not available.

### Dollar rate preference

The app stores three USD/ARS exchange rates (oficial, MEP, blue). A single user setting — **dollar rate preference** — controls which one is used for all USD↔ARS conversions. Default: MEP (the standard financial market rate in Argentina). This is a background preference, not a visible currency variant — the switcher shows plain `USD`.

| Preference | Rate pair         | Use case                        |
| ---------- | ----------------- | ------------------------------- |
| `oficial`  | `USD_ARS_OFICIAL` | Government/official rate        |
| `mep`      | `USD_ARS_MEP`     | Financial market rate (default) |
| `blue`     | `USD_ARS_BLUE`    | Informal/parallel market rate   |

## Architecture

### 1. Currency selection (frontend)

```
User clicks switcher → Zustand store updates → Cookie persisted (active-currency, 1yr)
                       → router.refresh() triggers server component re-render
```

- **Store**: `lib/stores/currency-store.ts` — Zustand with `activeCurrency` state.
- **Cookie**: `ACTIVE_CURRENCY_COOKIE = 'active-currency'` — read by server components.
- **Switcher**: `_components/currency-switcher.tsx` — collapsible ToggleGroup of `displayCurrencies`. Expanded: label, pill toggle, note. Collapsed: currency code + inline pill toggle. Collapsed state persisted via cookie (`currency-collapsed`), read server-side to avoid hydration flash.
- **Layout**: `(protected)/layout.tsx` — reads Settings API for primary/secondary, resolves `displayCurrencies` array, reads cookie for active selection.

### 2. Server component data flow

Each page reads the cookie and passes `currency` to API functions:

```
page.tsx → cookies().get('active-currency') → 'USD' | 'ARS' | 'original'
         → if 'original': pass undefined (no conversion) or fall back to primary (dashboard)
         → if currency: pass to API as ?currency=USD
```

- **Snapshots page**: passes `currency` to `getSnapshotGrid({ currency })`.
- **Investor dashboard**: passes `currency` to all metric endpoints. When "Original" is selected, falls back to the user's primary currency from Settings (aggregated metrics require a common currency).
- **Expenses page**: passes `currency` to `getExpenses({ currency })`. Table shows `convertedAmount` when a display currency is active, original `amount` otherwise. Currency column removed — the switcher indicates the display currency.
- **Income page**: same pattern as expenses — passes `currency` to `getIncome({ currency })`.
- **Financial dashboard**: passes `currency` to all finance metric endpoints (`/finance-metrics/overview`, `/monthly`, `/expense-breakdown`, `/income-breakdown`). Multi-currency entries are aggregated into the display currency via `_sum_converted()` helper using the same `convert_value` + `get_rate_map` pipeline. Same "Original" → primary fallback as the investor dashboard.

### 3. Backend conversion (date-aware as of Phase 3, Step C)

All conversion happens at query time in the service layer. Stored values are never modified. **Conversion uses the FX rate that was in effect on the value's own date**, not today's rate, so historical dashboards stay deterministic across time.

```
Router reads user's dollar_rate_preference from settings
  → calls mh.build_rate_lookup(session, dollar_preference)  # one DB round-trip per request
  → lookup pre-loads every stored rate, grouped by pair, sorted by date

Per row / per snapshot / per cashflow:
  → rate_map = lookup.get_rate_map_at(row.date)
  → mh.convert_value(value, from_currency, to_currency, rate_map)
     → Converts through USD as pivot:
       from → USD (divide by from_rate) → to (multiply by to_rate)
     → Same currency: return unchanged
     → Unsupported pair: return unchanged
```

The `RateLookup` finds "the latest rate where `rate.date <= as_of_date`" per pair via binary search. If `as_of_date` predates every stored rate, it falls back to the earliest available rate so the page never breaks. Per-date rate maps are memoised so repeated lookups for the same date are O(1).

**Which date a value converts at, by use case:**

| Use case                                               | Conversion date                               | Why                                                                                                                                                |
| ------------------------------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Expense / income list display                          | row's `date`                                  | Past records — historical accuracy.                                                                                                                |
| Snapshot grid cell / transaction                       | row's own `date`                              | Historical accuracy.                                                                                                                               |
| Asset price lookup                                     | `price.date`                                  | Historical accuracy.                                                                                                                               |
| Payments Calendar `card_due` event                     | item's event `date` (could be past or future) | Past months use historical rates; future dates fall back to latest stored.                                                                         |
| Portfolio TWR / IRR                                    | each snapshot / cashflow at its OWN date      | Chain math reflects real historical FX exposure.                                                                                                   |
| Per-month evolution chart                              | each month-end                                | Each historical month uses its own period-end rate.                                                                                                |
| Subscription / installment / payment obligation amount | today                                         | Forward-looking planning entities — what does this cost me NOW.                                                                                    |
| Card balance display (running total)                   | today                                         | Current state — today's rate is what makes sense for a "what do I owe right now" view.                                                             |
| Finance-metrics period totals (category breakdowns)    | `date_to` (period end)                        | Period-summary aggregates lose per-row dates at the DB layer; anchor to period end is a coarser-than-per-row compromise documented in the service. |

- **Helpers**: `utils/metrics.py` — `convert_value()`, `can_convert()`, `RateLookup`, `build_rate_lookup()`, `get_rate_map()` (kept as a backward-compat shim returning today's rate map).
- **Shared utility**: `utils/settings.py` — `get_dollar_pref(session, user_id)` reads the user's dollar rate preference from settings. Used by all routers that support currency conversion (metrics, snapshot_grid, expenses, income, payments_calendar, asset_prices, etc.).
- **Domain**: `domain/currency.py` — `SUPPORTED_CURRENCIES`, `get_ars_pair(preference)` maps dollar preference to `ExchangeRatePair`, `is_supported(code)`.
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

**Expenses and income** follow the same principle: the API response includes both `amount` (original) and `converted_amount` (display). The edit form always populates from `amount`, and the delete confirmation shows the original amount. Amount values are formatted with `String(Number())` in forms (strips trailing `.00`) and `formatAmount()` with `Intl.NumberFormat` in tables (adds thousand separators).

### 4.1 Investment currency lock

An investment's `base_currency` cannot be changed once snapshots exist — changing it would silently corrupt all stored values (e.g., 50 USD becomes 50 ARS). The backend rejects currency changes with 409 Conflict when snapshots exist. The frontend disables the currency combobox on the edit form (with a tooltip explaining why). Investments with zero snapshots can freely change currency.

### 5. Exchange rate fetching

Exchange rate providers follow the standardized provider pattern — see [external-providers.md](external-providers.md). Provider-specific logic (URLs, response parsing, field mapping) lives in `services/exchange_rate_providers.py`. The service layer (`services/exchange_rate_service.py`) iterates registered providers and stores results with zero provider knowledge.

**Current providers:**

- **DolarApi** (`dolarapi.com/v1/dolares`) → USD/ARS oficial, MEP, blue rates. Average of buy/sell.
- **Frankfurter** (`frankfurter.dev`) → USD/BRL, USD/EUR, USD/GBP rates. ECB data.

**Schedule:**

- **On startup**: immediate fetch (`next_run_time=datetime.now()`).
- **Every 6 hours**: APScheduler interval job.
- **Storage**: `exchange_rates` table with unique constraint on `(date, pair)`. Upsert on each fetch.
- **Pairs**: `USD_ARS_OFICIAL`, `USD_ARS_MEP`, `USD_ARS_BLUE`, `USD_BRL`, `USD_EUR`, `USD_GBP` (enum `ExchangeRatePair`).

### 6. Settings form — currency configuration

The Preferences page (`/preferences`) has a two-column layout. The left column handles currency configuration:

- **Primary currency**: required. The default display currency (shown first in the switcher, used as fallback when "Original" is selected on the dashboard).
- **Secondary currency**: optional. Shown as the second option in the sidebar switcher.
- **Dollar rate**: dropdown with Oficial / MEP / Blue. Controls which USD/ARS rate is used for all conversions. Default: MEP (from env var `NEXT_PUBLIC_FALLBACK_DOLLAR_RATE`).
- **Preferred currencies**: comma-separated ISO codes. Shown in their own group at the top of the currency combobox.
- **Shortcut currencies** (Integrations page): configurable list of currencies shown in the iOS Shortcut currency picker. Stored as `shortcut_currencies` in the settings JSONB. Defaults to primary + secondary when not set (backend fallback in `_settings_to_response`).

Both primary/secondary fields use a `CurrencyCombobox` with flag emoji, ranked search, and the full ISO 4217 allowlist. The env fallback currencies (`NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY` / `NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY`) are pinned at the top in a stable "Common" group. The backend stores the selected codes in `user_settings` via `PUT /settings`.

**How the switcher options are built** (in `(protected)/layout.tsx`):

1. Load settings from API → `primary` and `secondary`.
2. Build `displayCurrencies = [primary, secondary?, 'original']`.
3. Read `active-currency` cookie → if the saved value isn't in `displayCurrencies`, default to `primary`.
4. Pass `displayCurrencies` and `activeCurrency` to the sidebar switcher.

If no settings exist yet (first login), fallback env vars are used: `NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY` (default `ARS`) and `NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY` (default `USD`).

### 7. Unsupported currency warnings

Only USD, ARS, BRL, EUR, and GBP have exchange rate support. When a user selects any other currency, warnings appear at three points:

**Settings form (passive + on selection):**

- An animated `AlertTriangle` icon (amber, scale animation) appears next to the label of each combobox when its selected currency is unsupported.
- When either currency is unsupported, a `WarningHint` block appears below both comboboxes (separated by a `Separator`) with the text: _"Currencies that don't have exchange rate support yet. Conversion will be available soon."_
- On selection of an unsupported currency, a **warning toast** (amber) is shown: _"Exchange rate conversion for {CURRENCY} is not available yet. Values will be shown in their original currency."_

**Currency switcher (on switch):**

- When the user switches to an unsupported currency via the sidebar, a **warning toast** (amber) is shown: _"Conversion to {CURRENCY} is not available yet. Showing values in original currency."_

**Fallback behaviour:**

- When conversion is not possible, all monetary values fall back to their `base_currency` (same as "Original" mode). No error — the page renders normally, just without conversion.

**Supported check:** `lib/utils/currency.ts` — `isCurrencySupported()` checks against `['USD', 'ARS', 'BRL', 'EUR', 'GBP']`.

### 8. Unconvertible investments in metrics

When the dashboard requests metrics in a specific currency (e.g. ARS), investments with a base currency that can't be converted (e.g. CHF) are **excluded** from all aggregated metrics to avoid silently summing mixed currencies.

**Backend flow:**

1. `can_convert(from, to)` in `utils/metrics.py` checks if both currencies are in `SUPPORTED_CURRENCIES`.
2. `_split_by_convertibility()` in `metrics_service.py` splits investments into convertible and skipped lists.
3. Only convertible investments are used for computation. Skipped investments are returned in `skipped_investments` on every response.
4. If conversion is needed but no exchange rates exist in the DB, `ExchangeRateUnavailableError` (503) is raised.

**Frontend handling:**

- The dashboard shows a `WarningHint` listing skipped investments: _"Some investments were excluded because their currency can't be converted: Name (EUR)."_
- A `DismissableCurrencyHint` (`InfoHint` with `surface` background) appears on dashboard and snapshots pages when a non-original currency is selected, explaining that past values are converted at today's rate. Dismissable permanently via localStorage (`currency-hint-dismissed` key).
- If the API returns 503 (no rates at all), the dashboard shows a generic error fallback: _"Unable to load dashboard data."_

### 9. Multi-currency pivot conversion

All rates are stored against USD; any pair converts through USD as pivot.

**Rate sources:**

- **DolarApi** → USD/ARS (oficial, MEP, blue) — fetched on startup + every 6h.
- **Frankfurter** → USD/BRL, USD/EUR, USD/GBP — fetched on the same schedule.

**Pivot example:** BRL → ARS = BRL → USD (divide by USD/BRL rate) → ARS (multiply by USD/ARS rate).

**Rate map:** `get_rate_map(session, dollar_preference)` builds a `{currency: Decimal}` dict where each value means "1 USD = X currency". USD itself is always 1. The `dollar_preference` param determines which USD/ARS rate pair to use.

**Combobox:** The env fallback currencies are pinned at the top in a stable "Common" group. User-configured preferred currencies appear in a "Preferred" group below. All other currencies appear in an "Other currencies" group.

### 10. Edge cases summary

| Scenario                         | Behaviour                                      |
| -------------------------------- | ---------------------------------------------- |
| All investments USD, display ARS | All converted via the preferred dollar rate    |
| Mixed USD+ARS, display ARS       | Both converted correctly                       |
| EUR investment, display ARS      | Converted via pivot (EUR→USD→ARS)              |
| CHF investment, display ARS      | CHF investment excluded, warning shown         |
| Display currency CHF             | All investments excluded, warning lists all    |
| All investments same as display  | No conversion needed, no rate fetched          |
| No exchange rates in DB          | 503 error, dashboard shows load error fallback |
| "Original" selected on dashboard | Falls back to primary currency, hint shown     |
| "Original" on snapshots page     | No conversion, values in base currency         |

### 11. Credit card balance — per-currency buckets

Credit card balances are computed **per currency bucket**: each card carries one balance entry per currency that has activity on it, plus a primary-currency bucket (always present, zero when no activity). Each bucket's balance is `sum(expenses in this currency) - sum(settlements in this currency)`, with no cross-currency conversion at display time. This matches how Argentine resúmenes structure dual-balance cards (peso bucket + dólar bucket on the same physical card).

Single-currency cards collapse to one bucket — visually identical to the pre-Phase-3 single-balance display, zero overhead for non-Argentine users.

**Backend flow:** `expense_repository.sum_by_credit_card_ids_grouped()` and `card_settlement_repository.sum_by_card_ids_grouped()` both return `{card_id: {currency: amount}}`. `compute_card_balances()` (pure function in `credit_card_service.py`) subtracts settlements from expenses inside each bucket and orders the result primary-first. `get_card_balances()` orchestrates the DB queries — no rate map needed at this layer because buckets are never converted across currencies.

**Dashboard aggregation:** consumers that need a single-currency total (general dashboard, finance metrics) iterate every bucket and convert each one independently via `convert_value()` (USD pivot) using the user's dollar rate preference. The conversion happens at the consuming layer, not on the card-balance API.

**Front-end UX guards:** the settlement form shows a currency picker only when a card has > 1 bucket (otherwise it locks to primary silently). The expense form intercepts submit when a credit-card expense uses a currency the card hasn't seen before — the soft confirmation catches typos that would create phantom buckets.

## Data model

```sql
-- Each investment has a base currency
investments.base_currency  -- e.g. 'USD', 'ARS', 'BRL'

-- Snapshots and transactions store values in the investment's base currency
investment_snapshots.value     -- always in base_currency
investment_snapshots.currency  -- same as investment.base_currency
transactions.amount            -- always in base_currency
transactions.currency          -- same as investment.base_currency

-- Exchange rates fetched from DolarApi and Frankfurter
exchange_rates.pair   -- USD_ARS_OFICIAL | USD_ARS_MEP | USD_ARS_BLUE | USD_BRL | USD_EUR | USD_GBP
exchange_rates.rate   -- e.g. 1250.50 (1 USD = 1250.50 ARS)
exchange_rates.date   -- rate date
```
