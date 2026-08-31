# Currency Handling in Renly

## User-facing behaviour

The global currency switcher in the sidebar offers three options (configured in Preferences):

| Option                            | What the user sees                                                                                                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Primary currency** (e.g. ARS)   | All values converted to ARS                                                                                                                                                                |
| **Secondary currency** (e.g. USD) | All values converted to USD                                                                                                                                                                |
| **Original (X)**                  | Per-investment pages show each investment in its `base_currency`. The dashboard falls back to the primary currency (since aggregated metrics can't sum mixed currencies) and shows a hint. |

### Supported currencies

Five currencies have exchange rate support: **USD**, **ARS**, **BRL**, **EUR**, **GBP**. Any pair converts through USD as pivot (see Multi-currency pivot conversion below). The single source of truth is the **`Currency` enum** (`app/models/investment.py`); `app/domain/currency.py` derives `SUPPORTED_CURRENCIES` from it (`frozenset(c.value for c in Currency)`) so the two can never drift, and serves the set via `GET /exchange-rates/currencies`.

**Entry forms** (expense / income / subscription / installment / payment obligation) **and the investment form** (`base_currency`) only OFFER the supported set — the full-ISO "Other currencies" group is hidden there, and the API rejects an unsupported currency with **422** (finance entries and `base_currency` share the `validate_supported_currency` field-validator; snapshot/transaction rows are typed by the `Currency` enum). The "warning icon + fall back to original" behaviour below applies only to the **display and preference** pickers (which keep the full ISO list): a currency without exchange-rate support can still be selected for display/preferences and simply shows unconverted.

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

The display `currency` query param is **case-insensitive**: every read endpoint takes it through a shared `DisplayCurrency` dependency (`app/deps/currency.py`) that uppercases it before conversion, so a direct or third-party caller sending `?currency=usd` converts identically to `?currency=USD` instead of silently skipping conversion (the rate maps are uppercase-keyed). The asset-price `convert_to` param is normalized the same way. The web always sends uppercase.

- **Snapshots page**: passes `currency` to `getSnapshotGrid({ currency })`.
- **Investor dashboard**: passes `currency` to all metric endpoints. When "Original" is selected, falls back to the user's primary currency from Settings (aggregated metrics require a common currency).
- **Expenses page**: passes `currency` to `getExpenses({ currency })`. Table shows `convertedAmount` when a display currency is active, original `amount` otherwise. Currency column removed — the switcher indicates the display currency.
- **Income page**: same pattern as expenses — passes `currency` to `getIncome({ currency })`.
- **Financial dashboard**: passes `currency` to all finance metric endpoints (`/finance-metrics/overview`, `/monthly`, `/expense-breakdown`, `/income-breakdown`). Multi-currency entries are aggregated into the display currency via `_sum_converted()` helper using the same `convert_value` + `RateLookup` pipeline. Same "Original" → primary fallback as the investor dashboard.

### 3. Backend conversion (date-aware as of Phase 3, Step C)

All conversion happens at query time in the service layer. Stored values are never modified. **Conversion uses the FX rate that was in effect on the value's own date**, not today's rate, so historical dashboards stay deterministic across time.

```
Service builds one rate lookup per request (routers just pass currency through)
  → exchange_rate_service.get_user_rate_lookup(session, user_id)  # reads dollar pref + one DB round-trip
  → lookup pre-loads every stored rate, grouped by pair, sorted by date
  # Dashboard overview/composition/liquidity fold the dollar pref + timezone + liquidity threshold
  # into ONE user_settings read via settings_service.get_request_settings, then build the lookup
  # from the pre-read dollar preference — one settings round-trip instead of two or three.

Per row / per snapshot / per cashflow:
  → rate_map = lookup.get_rate_map_at(row.date)
  → mh.convert_value(value, from_currency, to_currency, rate_map)
     → Converts through USD as pivot:
       from → USD (divide by from_rate) → to (multiply by to_rate)
     → Same currency: return unchanged
     → Unsupported pair: return unchanged
```

The `RateLookup` finds "the latest rate where `rate.date <= as_of_date`" per pair via binary search. If `as_of_date` predates every stored rate, it falls back to the earliest available rate so the page never breaks. Per-date rate maps are memoised so repeated lookups for the same date are O(1).

**Grouped-rates cache.** The full grouped-by-pair load that backs every `RateLookup` is served from a process-level TTL cache (`RATES_CACHE_TTL_SECONDS = 600`) in `exchange_rate_service.get_rates_grouped_by_pair_cached`. Rates are global (not per-user) and only change when the 6-hourly scheduler stores fresh quotes, so this stops every converting endpoint from re-reading the whole `exchange_rates` table per request. `exchange_rate_service.invalidate_rates_cache()` is called right after the scheduler upserts fresh rates so they serve immediately instead of waiting out the TTL. The composite index `idx_exchange_rates_pair_date (pair, date)` serves the per-pair, date-ordered scan (the pre-existing `idx_exchange_rates_date` on `date DESC` alone cannot).

**Fail-loud conversion.** `convert_value` returns `Decimal | None` — `None` when either currency's rate is missing from the map. A value is **never** summed unconverted. Callers handle `None` by skipping and reporting:

- **Aggregates** (finance overview / monthly / breakdowns, dashboard overview / evolution / composition, expense & income lists, payments calendar) exclude the row and list its code in an additive `skipped_currencies: string[]` response field.
- **Liquidity** reuses `skipped_entities` (a new `income` entry type carries the currency code as its name).
- **Metrics & snapshot grid** extend the data-presence-aware `skipped_investments` — an investment whose base or the display currency has no stored rates is excluded and surfaced.
- **Per-row `converted_*` fields** (expense/income/plan/calendar rows, asset-price lookup) stay **null** on a missing rate, never the unconverted number.
- **Single-investment metrics** raise `ExchangeRateUnavailableError` (503) rather than silently drop conversion.
- **A pot's value (NAV)** is `null` unless it can be stated in full. It is a SUM, and a sum missing a term is not a smaller sum — so an unconvertible holding, a holding nobody has valued on or before the date, or no holdings at all all answer `null` rather than a partial figure. That matters beyond display: units are issued against this number, so a partial one moves real value between co-owners. An **archived** holding is excluded from the sum by design and so never makes it unknown.
- **A pot's value SERIES** applies that same rule per point, through the same function (`pot_service._add_holdings`), which is the reason it is one function: a series computed by a second copy of the refusal rule is a second algorithm that has to agree with the first at every date. Each point converts at **its own** date's rate map, so re-opening the page tomorrow shows the same historical figures.

**Which date a value converts at, by use case:**

| Use case                                                | Conversion date                               | Why                                                                                                                                                |
| ------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Expense / income list display                           | row's `date`                                  | Past records — historical accuracy.                                                                                                                |
| Snapshot grid cell / transaction                        | row's own `date`                              | Historical accuracy.                                                                                                                               |
| Asset price lookup                                      | `price.date`                                  | Historical accuracy.                                                                                                                               |
| Payments Calendar `card_due` event                      | item's event `date` (could be past or future) | Past months use historical rates; future dates fall back to latest stored.                                                                         |
| Portfolio TWR / IRR                                     | each snapshot / cashflow at its OWN date      | Chain math reflects real historical FX exposure.                                                                                                   |
| Per-month evolution chart                               | each month-end                                | Each historical month uses its own period-end rate.                                                                                                |
| Pot value series point                                  | that point's own date                         | Same rule as the evolution chart, on the pot's cadence grid rather than a month grid.                                                              |
| Subscription / installment / payment obligation amount  | today                                         | Forward-looking planning entities — what does this cost me NOW.                                                                                    |
| Liquidity-alert fixed commitments (amortised totals)    | today                                         | Same rationale as subscriptions / installments / obligations — the alert evaluates current commitment load against current income.                 |
| Liquidity-alert monthly income window total             | today (window-end anchor)                     | Single conversion anchor for the multi-currency window sum; matches `_sum_converted` semantics used elsewhere for period totals.                   |
| Card balance display (running total)                    | today                                         | Current state — today's rate is what makes sense for a "what do I owe right now" view.                                                             |
| Shared balance glance figure (per currency bucket)      | today                                         | A balance is a live position: the expenses behind it are already reduced to one figure per bucket, with no single date to convert at.              |
| Overpay waterfall — pricing a bucket the excess reaches | the PAYMENT's `date`                          | A payment happened on a day, and that is the rate at which the money actually moved. Deliberately unlike the row above, which is a live position.  |
| Finance-metrics period totals (category breakdowns)     | `date_to` (period end)                        | Period-summary aggregates lose per-row dates at the DB layer; anchor to period end is a coarser-than-per-row compromise documented in the service. |

- **Helpers**: `utils/metrics.py` (pure, no DB) — `convert_value()`, `convert_optional()`, `can_convert()`, `RateLookup`. Rate loading (`build_rate_lookup()` / `get_user_rate_lookup()`) lives in `exchange_rate_service`; the old `get_rate_map()` shim was removed.
- **Shared utility**: `get_dollar_pref(session, user_id)` and `get_liquidity_threshold(session, user_id)` live in `settings_service` (the former `utils/settings.py` was removed). They are read by services — via `exchange_rate_service.get_user_rate_lookup` — not by routers.
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

### 4.2 Snapshot / transaction row currency must equal the investment base

A snapshot or transaction valued in a currency other than its investment's `base_currency` would misvalue every downstream metric (~1000× for ARS↔USD). The snapshot-upsert and transaction create/update paths reject a mismatch with **400** (`InvestmentCurrencyMismatchError`, message `Currency <X> does not match the investment's base currency (<Y>).`); there is no auto-convert. The snapshot/transaction **importers** apply the same rule per row — a mismatched row is flagged invalid with the same message (the resolver knows each investment's base currency).

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

**Supported check:** the frontend never hardcodes the supported set — it receives it from `GET /exchange-rates/currencies` (derived from the `Currency` enum, the single source of truth) as a `supportedCurrencies: string[]` prop, and each display/preference picker checks membership inline (`supportedCurrencies.includes(code)`; see the `isSupported` helper in `preferences-form.tsx` and the switch guard in `currency-switcher.tsx`). When the set is unavailable it fails open (treats every code as supported).

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

**Rate map:** `RateLookup.get_rate_map_at(as_of_date)` returns a `{currency: Decimal}` dict for the rates in effect on that date, where each value means "1 USD = X currency". USD itself is always 1. The lookup's `dollar_preference` determines which USD/ARS rate pair to use.

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

**A converted bucket is a mark, not a settlement quote — and the two can diverge in either direction.** That conversion uses the user's **display** preference, while the bill is actually extinguished at the **card** rate (oficial x the perception, §12). So clearing a foreign bucket moves reported net worth by the difference, and the SIGN depends on the rate regime, not on the preference alone: a gain appears only when the chosen rate's premium over oficial exceeds the perception (~30%). Measured on a US$100 bucket — at the 2026-08 regime (oficial 1485, MEP 1515.60, a 2.1% premium) settling REDUCES net worth by 41,490; in a high-gap regime (oficial 800, MEP 1500, an 87.5% premium) it reads as a 46,000 GAIN. The arithmetic is consistent mark-to-market and invents nothing, and reconciliation cannot absorb it (both the cash and bucket figures are already exact). Renly discloses this rather than re-marking: Help's currency section says a foreign-currency card balance is what you owe today, not a quote for clearing it. **Renly keeps the mark-to-market and discloses it rather than re-marking the bucket at the card rate.** Re-marking would make settlement net-worth-neutral in every regime, but it would couple `NEXT_PUBLIC_CARD_PERCEPTION_MULTIPLIER` — a display-only variable — into the net-worth headline, the evolution chart, the composition donut, and the month-over-month delta, and it would apply an Argentine tax rate to users in other countries. The net-worth figures are deliberately country-agnostic: no Argentina-specific tax rate belongs in them. Since there is no misstatement in the current regime, that is a certain cost against a latent one. **The condition under which re-marking becomes worth it: a sustained parallel-dollar premium over oficial above the perception (~30%)**, at which point clearing a foreign bucket starts reading as a gain and either re-marking or itemising the FX/tax gap as its own line earns its keep.

**Front-end UX guards:** the settlement form shows a currency picker only when a card has > 1 bucket (otherwise it locks to primary silently). The expense form intercepts submit when a credit-card expense uses a currency the card hasn't seen before — the soft confirmation catches typos that would create phantom buckets.

### 12. Cross-currency card settlement — two amounts, no stored rate

Paying a bucket from an account in a **different** currency (the Argentine "dólar tarjeta" case: a USD bill paid with pesos) is the one place a single amount cannot describe what happened. The bank converts internally, so the bill is cleared in the **bucket's** currency while a different figure leaves the account.

`card_settlements` therefore carries two amounts: `amount`/`currency` (the **card leg**, what cleared the bucket) and the nullable `account_amount` (the **cash leg**, in the funding account's own currency, set only when the two differ). **No rate is stored** — the same conclusion `transfers` reached with `from_amount`/`to_amount`: no single direction reads correctly both ways, and the division has unbounded precision. The pair _is_ the rate record, and the gap between the two legs is the real FX + tax cost of the payment, and it is never itemised. Note what that does to the reported net-worth DELTA: outstanding card debt is marked at the user's dollar-rate preference, so clearing it reduces net worth when the debt was marked BELOW the card rate (oficial) and can read as a gain when it was marked at or above it (MEP, blue — MEP is the default). Either way the arithmetic is consistent mark-to-market and no figure is invented; the ~30% Ganancias perception is inside the blended rate with nothing separable to record. Reconciliation remains the generic tax/fee catch-all for anything that really is a separate charge.

**Which leg each sum reads is the whole correctness surface.** Three sums are cash-side and read `coalesce(account_amount, amount)` — `card_settlement_repository.sum_by_account_ids` (which serves both the live account balance and reconciliation's point-in-time balance), `sum_by_account_ids_monthly` (the net-worth chart), and `account_movement_repository._settlement_branch` (the per-account ledger). Four are card-side and read `amount` alone — `sum_by_card_ids_grouped`, `sum_by_card_ids_monthly`, and the bucket-balance sums in `card_reconciliation_repository`. Swapping either direction is a silent money bug: a cash sum reading the card leg would add dollars into a peso balance, and a card sum reading the cash leg would clear a USD bucket with a peso figure. `tests/unit/test_cross_currency_settlement.py` pins the split by compiling the real SQL, and the env-gated `tests/integration/test_account_ledger_drift.py` proves it against a real Postgres.

**Display estimate only:** the settlement dialog reads back the rate the two typed amounts imply and compares it with `oficial × NEXT_PUBLIC_CARD_PERCEPTION_MULTIPLIER` (default 1.30), purely so a 10× typo is visible. It reads the `USD_ARS_OFICIAL` pair specifically, **not** the user's dollar-rate preference — dólar tarjeta is built on oficial even for a user viewing MEP. Nothing is prefilled and no stored value depends on the multiplier.

### 13. Shared balances — per-currency buckets that never net

A group's balances are kept in **per-currency buckets**, exactly as a card's are, and for the same reason: owing dollars while being owed pesos is a real state, and merging the two would invent a rate nobody agreed to. Each bucket is its own settle line and its own zero-sum. A member can be a creditor in one and a debtor in another simultaneously, which `GET /groups/{id}/balances` returns as separate entries rather than one netted figure.

The converted figure beside a bucket (`my_converted_balance`) is a **display convenience only** — a mark at the viewer's own dollar-rate preference, never what anybody settles. It is computed at TODAY's rate rather than at each contributing expense's, because a balance is a live position rather than a historical row: the expenses behind it have already been reduced to one figure per bucket, and there is no single date to convert it at. A bucket with no usable rate reports `null` and its currency appears in `skipped_currencies`, matching how the expenses list flags an unconvertible row.

**A settlement carries up to three amounts, and each answers a different question.** `amount`/`currency` is the **bucket leg** — which balance it cleared and by how much. `from_amount` is the **payer's cash leg** in that account's own currency, and `to_amount` the **payee's**, each set only when that side crossed currencies. Same conclusion `card_settlements` and `transfers` reached: **no rate is stored**, because no single direction reads correctly both ways, and the pair of amounts is the record of it.

Three legs rather than two because a settlement moves money between **two different people's** accounts, and the two can cross currencies independently — Nico pays a 40 USD balance out of his peso account into my dollar account, and all three figures differ. It is also why neither side can fill in the other's: the row-level policies hide each member's accounts from the other, so each records their own (`400 group_settlement_foreign_leg`).

**Which leg each sum reads is the whole correctness surface,** the same way it is for card settlements. Both cash-side sums read `coalesce(<leg>_amount, amount)` — `group_settlement_repository._sum_leg` (the live account balance and the point-in-time one) and `_sum_leg_dated` (the balance series) — while the balance derivation reads `amount` alone, because that is what cleared the bucket. A cash sum reading the bucket leg would take pesos out of a dollar account; the balance reading a cash leg would clear a USD bucket with a peso figure. `tests/integration/test_shared_flow_queries.py` drives both against a real Postgres, with one cross-currency settlement whose three figures all differ so a query reading the wrong column shows up as the two accounts moving by each other's amount.

**A shared expense is single-currency by construction.** Its amount, its splits and its balance bucket are all the same currency, and its funding account must match it (`400 account_currency_mismatch`) — the account sum carries one amount, so a mismatched link would subtract a foreign figure straight from the balance. Only the **settlement** crosses currencies, which is where the conversion belongs: it is the moment somebody actually agreed a rate.

**Every figure the balances surface renders names its own currency, and that is not decoration.** A bucket's amounts carry no code of their own (the bucket's badge says which), so the converted glance beside them has to state its currency or the two read as one scale — "≈ 32.48" next to "50,000" is two numbers in two currencies with nothing on screen telling them apart. The same rule makes the group's expense and settlement tables append the code to each money cell: both hold every currency the group has ever used, side by side and never converted, so a bare `120` beside a bare `90,000` would leave the reader to guess which is dollars. And where a row's own amount IS converted — a shared row in `/expenses` — the sub-line restates the share _and_ the whole in the row's original currency, so it stays a complete fact rather than inviting a ratio against the converted figure above it. `skipped_currencies` is stated out loud for the same reason: a bucket that carries no glance while its neighbour does deserves the reason rather than a guess.

### 14. Overpay waterfall — one payment, several buckets, no stored rate

A payment larger than the balance it names has an excess, and if the payer owes the payee in other
currencies that excess can clear those too. `POST /groups/{id}/settlements/preview` prices each
reachable bucket in the currency being paid; `POST …/waterfall` records one settlement per bucket.

**Which rate.** The bucket's outstanding amount is converted into the payment's currency at the rate in
force on the **payment's date** — not today's, which is what the glance figure beside a balance uses.
The two are different questions: a displayed balance is a live position with no single date behind it,
whereas a payment happened on a day. A bucket with no usable rate is named in `skipped_currencies` and
left alone rather than converted at a guess.

**No stored rate, and no rate needed twice.** Each candidate carries two figures — what is owed, and
what clearing it costs in the currency being paid — and the allocator works from their ratio, so a
partial allocation cannot round differently from a full one. The invariant it guarantees: **the steps'
costs plus the leftover equal the excess exactly**, in the currency the payment was made in.

**The cash leg.** One real payment has one account movement, stated once and divided across the rows in
proportion to what each consumed of the payment — never re-converted at a market rate, so a payment made
at the rate the payer's bank gave them stays recorded at that rate. A row whose bucket is already in the
account's own currency crosses nothing, so it moves exactly what it clears and only the rows that DID
cross split what is left; each of those still needs at least one minor unit, so a stated total too small
to give every row something is refused (`400 group_settlement_leg_total_too_small`) and a share that
merely rounds below one unit is lifted to one, taken off the largest part.

## Data model

```sql
-- Each investment has a base currency
investments.base_currency  -- e.g. 'USD', 'ARS', 'BRL'

-- Snapshots and transactions store values in the investment's base currency
investment_snapshots.value     -- always in base_currency
investment_snapshots.currency  -- same as investment.base_currency
transactions.amount            -- always in base_currency
transactions.currency          -- same as investment.base_currency

-- A pot's base currency: the unit ALL its ownership maths runs in. Not updatable, because it is
-- the unit of every figure already recorded in its ledger. Changing a DISPLAY currency re-converts
-- what you see and never moves ownership.
pots.base_currency             -- e.g. 'USD'
pot_ownership_events.amount    -- what left, in the source account's currency
pot_ownership_events.amount_currency  -- NULL when it equals the pot's base currency
pot_ownership_events.base_amount      -- what was credited, in the pot's base currency

-- A shared expense is single-currency: amount, splits and balance bucket all agree, and the funding
-- account must match. Only a SETTLEMENT crosses currencies, which is where a rate is actually agreed.
shared_expenses.currency          -- the expense, its splits, and the bucket it lands in
group_settlements.amount          -- the bucket leg: what balance was cleared, and by how much
group_settlements.currency        -- the bucket's currency, not either account's
group_settlements.from_amount     -- the payer's cash leg; NULL when their account matched the bucket
group_settlements.to_amount       -- the payee's cash leg; NULL when theirs did

-- Exchange rates fetched from DolarApi and Frankfurter
exchange_rates.pair   -- USD_ARS_OFICIAL | USD_ARS_MEP | USD_ARS_BLUE | USD_BRL | USD_EUR | USD_GBP
exchange_rates.rate   -- e.g. 1250.50 (1 USD = 1250.50 ARS)
exchange_rates.date   -- rate date
```
