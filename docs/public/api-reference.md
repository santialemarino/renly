# Renly API Reference

All endpoints require authentication via a Bearer token (JWT) in the `Authorization` header, except for `POST /auth/register` and `POST /auth/login`. Some endpoints also accept API key authentication (see API Keys section).

Base URL: `/api` (all paths below are relative to this).

---

## Authentication

| Method | Path             | Description                                               |
| ------ | ---------------- | --------------------------------------------------------- |
| `POST` | `/auth/register` | Create a new account. Returns a JWT.                      |
| `POST` | `/auth/login`    | Sign in with email and password. Returns a JWT.           |
| `POST` | `/auth/logout`   | Sign out. Invalidates all existing tokens for the user.   |
| `GET`  | `/auth/me`       | Returns the current authenticated user (id, name, email). |

---

## Investments

| Method  | Path                          | Description                                                                  |
| ------- | ----------------------------- | ---------------------------------------------------------------------------- |
| `GET`   | `/investments`                | List investments with filtering, search, and pagination.                     |
| `POST`  | `/investments`                | Create a new investment.                                                     |
| `GET`   | `/investments/{id}`           | Get a single investment by ID.                                               |
| `PUT`   | `/investments/{id}`           | Update an investment. Only provided fields are changed.                      |
| `PATCH` | `/investments/{id}/archive`   | Archive an investment (hides it from the active portfolio).                  |
| `PATCH` | `/investments/{id}/unarchive` | Restore an archived investment.                                              |
| `PUT`   | `/investments/{id}/groups`    | Replace group membership for this investment. Body: `{ group_ids: [1, 3] }`. |

**List query parameters:**

| Parameter     | Type    | Default | Description                                                |
| ------------- | ------- | ------- | ---------------------------------------------------------- |
| `search`      | string  | --      | Filter by name (case-insensitive).                         |
| `group_ids`   | int[]   | --      | Filter to investments in any of these groups.              |
| `category`    | string  | --      | Filter by category (e.g., `cedears`, `stocks`).            |
| `active_only` | boolean | `true`  | Whether to exclude archived investments.                   |
| `page`        | int     | `1`     | Page number (1-based).                                     |
| `page_size`   | int     | `20`    | Results per page (max 100).                                |
| `sort_by`     | string  | --      | Sort field: `name`, `category`, `base_currency`, `broker`. |
| `sort_order`  | string  | `asc`   | Sort direction: `asc` or `desc`.                           |

---

## Snapshots

Snapshots are nested under an investment. Each snapshot records the value of an investment at a point in time (typically end of month). There can only be one snapshot per investment per date.

| Method | Path                          | Description                                                                                      |
| ------ | ----------------------------- | ------------------------------------------------------------------------------------------------ |
| `GET`  | `/investments/{id}/snapshots` | List all snapshots for an investment, ordered by date.                                           |
| `POST` | `/investments/{id}/snapshots` | Create or update a snapshot (upsert). If a snapshot already exists for that date, it is updated. |

**Snapshot body fields:** `date`, `value`, `quantity` (optional), `currency`, `notes` (optional).

---

## Transactions

Transactions are nested under an investment. They represent money movements: buying more shares, selling, depositing additional capital, or withdrawing.

| Method   | Path                                     | Description                                             |
| -------- | ---------------------------------------- | ------------------------------------------------------- |
| `GET`    | `/investments/{id}/transactions`         | List all transactions for an investment.                |
| `GET`    | `/investments/{id}/transactions/{tx_id}` | Get a single transaction.                               |
| `POST`   | `/investments/{id}/transactions`         | Create a new transaction.                               |
| `PUT`    | `/investments/{id}/transactions/{tx_id}` | Update a transaction. Only provided fields are changed. |
| `DELETE` | `/investments/{id}/transactions/{tx_id}` | Delete a transaction.                                   |

**Transaction body fields:** `date`, `amount`, `quantity` (optional), `currency`, `type` (`buy`, `sell`, `deposit`, `withdrawal`), `notes` (optional).

---

## Snapshots Grid

The grid view shows all investments as rows and months as columns, similar to a spreadsheet. Each cell contains the value, period return, and whether there were transactions that month.

| Method | Path              | Description                                           |
| ------ | ----------------- | ----------------------------------------------------- |
| `GET`  | `/snapshots/grid` | Returns the full snapshots grid for the current user. |

**Query parameters:**

| Parameter    | Type   | Default | Description                                                                       |
| ------------ | ------ | ------- | --------------------------------------------------------------------------------- |
| `search`     | string | --      | Filter by investment name.                                                        |
| `group_ids`  | int[]  | --      | Filter by group IDs.                                                              |
| `category`   | string | --      | Filter by category.                                                               |
| `currency`   | string | --      | Display currency for conversion (e.g., `USD`, `ARS`). Omit for original currency. |
| `sort_by`    | string | --      | Sort field: `name`.                                                               |
| `sort_order` | string | `asc`   | Sort direction: `asc` or `desc`.                                                  |

---

## Groups

Groups are user-defined labels for organizing investments (e.g., "Retirement", "Trading", "Kids"). An investment can belong to multiple groups. Each group can have an optional target allocation percentage for the dashboard.

| Method   | Path                       | Description                                                                        |
| -------- | -------------------------- | ---------------------------------------------------------------------------------- |
| `GET`    | `/groups`                  | List all groups. Each group includes its investment IDs and target percentage.     |
| `POST`   | `/groups`                  | Create a new group. Optional: `target_percentage` (0-100).                         |
| `GET`    | `/groups/{id}`             | Get a single group with its investment IDs.                                        |
| `PUT`    | `/groups/{id}`             | Update a group. Fields: `name`, `target_percentage` (both optional).               |
| `DELETE` | `/groups/{id}`             | Delete a group.                                                                    |
| `PUT`    | `/groups/{id}/investments` | Replace the group's investment membership. Body: `{ investment_ids: [5, 12, 8] }`. |

**List query parameters:** `search` (filter by name), `sort_by` (`name`), `sort_order` (`asc`/`desc`).

**Group allocation metrics** (`GET /metrics/allocation/by-group`) include `target_percentage` and `difference` (actual minus target) for each group that has a target set.

---

## Income

| Method   | Path           | Description                                                 |
| -------- | -------------- | ----------------------------------------------------------- |
| `GET`    | `/income`      | List income entries with filtering, search, and pagination. |
| `POST`   | `/income`      | Create a new income entry.                                  |
| `GET`    | `/income/{id}` | Get a single income entry by ID.                            |
| `PUT`    | `/income/{id}` | Update an income entry. Only provided fields are changed.   |
| `DELETE` | `/income/{id}` | Delete an income entry.                                     |

**List query parameters:**

| Parameter    | Type   | Default | Description                                                       |
| ------------ | ------ | ------- | ----------------------------------------------------------------- |
| `search`     | string | --      | Filter by notes (case-insensitive).                               |
| `category`   | string | --      | Filter by income category (e.g., `salary`, `freelance`).          |
| `date_from`  | date   | --      | Start date (inclusive, YYYY-MM-DD).                               |
| `date_to`    | date   | --      | End date (inclusive, YYYY-MM-DD).                                 |
| `currency`   | string | --      | Display currency for conversion (e.g., `USD`). Omit for original. |
| `page`       | int    | `1`     | Page number (1-based).                                            |
| `page_size`  | int    | `25`    | Results per page (max 100).                                       |
| `sort_by`    | string | --      | Sort field: `date`, `amount`, `category`.                         |
| `sort_order` | string | `asc`   | Sort direction: `asc` or `desc`.                                  |

**Income categories:** `salary`, `freelance`, `bonus`, `investment_returns`, `dividends`, `rental_income`, `sales`, `refunds`, `gifts`, `other`.

---

## Expenses

| Method   | Path             | Description                                                   |
| -------- | ---------------- | ------------------------------------------------------------- |
| `GET`    | `/expenses`      | List expenses with filtering, search, and pagination.         |
| `POST`   | `/expenses`      | Create a new expense. **Supports both JWT and API key auth.** |
| `GET`    | `/expenses/{id}` | Get a single expense by ID.                                   |
| `PUT`    | `/expenses/{id}` | Update an expense. Only provided fields are changed.          |
| `DELETE` | `/expenses/{id}` | Delete an expense.                                            |

**List query parameters:**

| Parameter        | Type   | Default | Description                                                           |
| ---------------- | ------ | ------- | --------------------------------------------------------------------- |
| `search`         | string | --      | Filter by notes (case-insensitive).                                   |
| `category`       | string | --      | Filter by expense category (e.g., `food`, `transport`).               |
| `payment_method` | string | --      | Filter by payment method: `cash`, `debit`, `transfer`, `credit_card`. |
| `date_from`      | date   | --      | Start date (inclusive, YYYY-MM-DD).                                   |
| `date_to`        | date   | --      | End date (inclusive, YYYY-MM-DD).                                     |
| `currency`       | string | --      | Display currency for conversion (e.g., `USD`). Omit for original.     |
| `page`           | int    | `1`     | Page number (1-based).                                                |
| `page_size`      | int    | `25`    | Results per page (max 100).                                           |
| `sort_by`        | string | --      | Sort field: `date`, `amount`, `category`, `payment_method`.           |
| `sort_order`     | string | `asc`   | Sort direction: `asc` or `desc`.                                      |

**Expense categories:** `food`, `dining`, `transport`, `rent`, `utilities`, `health`, `entertainment`, `sports`, `subscriptions`, `clothing`, `education`, `personal_care`, `home_maintenance`, `gifts`, `travel`, `taxes`, `insurance`, `kids`, `pets`, `other`.

**Payment methods:** `cash`, `debit`, `transfer`, `credit_card`.

**Source:** The `source` field indicates how the expense was created: `manual` (default, web app), `shortcut` (iOS Shortcut), `auto`, or `email_parsed`. Sent in the request body on `POST /expenses`; returned in all responses.

**Amount validation:** `amount` must be greater than zero on all create and update endpoints (expenses, income, settlements). Returns 422 if zero or negative.

**Currency conversion:** When `currency` is provided, the response includes `converted_amount` per entry and `display_currency` on the list response. The original `amount` and `currency` are always preserved.

---

## Credit Cards

Credit cards are treated as liabilities. The balance is computed as: total expenses linked to the card minus total settlements (payments).

| Method   | Path                                   | Description                                                                                   |
| -------- | -------------------------------------- | --------------------------------------------------------------------------------------------- |
| `GET`    | `/credit-cards`                        | List credit cards with search, sorting, and balances. **Supports both JWT and API key auth.** |
| `POST`   | `/credit-cards`                        | Create a new credit card.                                                                     |
| `GET`    | `/credit-cards/{id}`                   | Get a single card with its current balance.                                                   |
| `PUT`    | `/credit-cards/{id}`                   | Update a card. Only provided fields are changed.                                              |
| `DELETE` | `/credit-cards/{id}`                   | Delete a card. Returns 409 if the card has linked expenses.                                   |
| `POST`   | `/credit-cards/{id}/archive`           | Archive a card (hide from active selection).                                                  |
| `POST`   | `/credit-cards/{id}/unarchive`         | Restore an archived card.                                                                     |
| `GET`    | `/credit-cards/{id}/settlements`       | List settlements (payments) for a card.                                                       |
| `POST`   | `/credit-cards/{id}/settlements`       | Record a new settlement.                                                                      |
| `DELETE` | `/credit-cards/{id}/settlements/{sid}` | Delete a settlement.                                                                          |

**List query parameters:** `search` (filter by name), `sort_by` (`name`, `closing_day`, `due_day`, `currency`), `sort_order` (`asc`/`desc`), `show_archived` (boolean, default `false` — include archived cards).

**Card fields:** `name`, `closing_day` (1-31), `due_day` (1-31), `currency` (ISO 4217 — the card's primary/statement currency), `is_active` (boolean), `has_expenses` (computed, read-only), `balances` (computed — list of `{currency, balance}` per currency with activity; primary always present, others added by expense activity in non-primary currencies; balances are NOT converted across currencies).

**Archive behavior:** Archived cards are hidden from the expense form's card selector but retain all linked expenses and settlements. Bucket balances are still computed normally. Delete is only allowed when the card has no linked expenses (409 otherwise).

**Settlement fields:** `date`, `amount`, `currency` (required — selects which bucket the settlement reduces), `notes` (optional).

---

## Subscriptions

Recurring charges (e.g. Netflix, Spotify, gym). The daily scheduler auto-generates one expense entry per billing cycle, advances `next_billing_date`, and back-fills missed cycles for subscriptions registered with a past `next_billing_date`.

| Method   | Path                  | Description                                                                       |
| -------- | --------------------- | --------------------------------------------------------------------------------- |
| `GET`    | `/subscriptions`      | List subscriptions with search, sorting, archive filter, and currency conversion. |
| `POST`   | `/subscriptions`      | Create a new subscription.                                                        |
| `GET`    | `/subscriptions/{id}` | Get a single subscription by ID.                                                  |
| `PUT`    | `/subscriptions/{id}` | Update a subscription. Only provided fields are changed.                          |
| `DELETE` | `/subscriptions/{id}` | Delete a subscription.                                                            |

**Query parameters (list):** `search`, `sort_by` (`name`, `amount`, `currency`, `billing_cycle`, `next_billing_date`), `sort_order` (`asc`/`desc`), `show_archived`, `currency` (display currency for conversion).

**Subscription fields:** `name`, `amount` (> 0), `currency` (ISO 4217), `billing_cycle` (`monthly`, `annual`, `quarterly`, `biweekly`, `weekly`), `payment_method` (optional; `cash`, `debit`, `transfer`, `credit_card`), `credit_card_id` (when payment_method = credit_card), `is_active`, `next_billing_date`. Responses also include `converted_amount` when `currency` query param is provided.

---

## Installments

Cuotas (installment plans, e.g. TV Samsung 12x). The daily scheduler auto-generates one expense entry per cuota and back-fills missed cuotas for plans registered with a past `start_date`.

| Method   | Path                 | Description                                                                           |
| -------- | -------------------- | ------------------------------------------------------------------------------------- |
| `GET`    | `/installments`      | List installment plans with search, sorting, archive filter, and currency conversion. |
| `POST`   | `/installments`      | Create a new installment plan.                                                        |
| `GET`    | `/installments/{id}` | Get a single installment plan by ID.                                                  |
| `PUT`    | `/installments/{id}` | Update an installment plan. Only provided fields are changed.                         |
| `DELETE` | `/installments/{id}` | Delete an installment plan.                                                           |

**Query parameters (list):** `search`, `sort_by` (`name`, `total_amount`, `installment_amount`, `currency`, `installments_count`, `current_installment`, `start_date`), `sort_order`, `show_archived`, `currency`.

**Installment fields:** `name`, `total_amount` (> 0), `installment_amount` (> 0), `currency`, `installments_count` (≥ 1), `current_installment` (≥ 1; default 1), `payment_method` (optional), `credit_card_id` (optional), `is_active`, `start_date`. Responses include `converted_total_amount` and `converted_installment_amount` when `currency` query param is provided.

**Lifecycle:** `is_active` flips to `false` automatically when the scheduler issues the last cuota (`current_installment > installments_count`). The user can also archive/unarchive a plan manually via `PUT /installments/{id}` with `is_active`.

**Locked fields:** Once `current_installment > 1` (any cuota has been charged), the contractual fields `total_amount`, `installment_amount`, `installments_count`, `currency`, `start_date`, `payment_method`, `credit_card_id` are locked. A `PUT` that attempts to change any of them returns `400` with `{"detail": "...", "code": "installment_locked_field", "fields": [...]}`. Always editable: `name`, `current_installment`, `is_active`.

---

## Payment Obligations

Recurring or one-off payment obligations (e.g. electricity, ABL, internet). Surfaces in the Payments Calendar (Phase 3, Step 4).

| Method   | Path                        | Description                                                                     |
| -------- | --------------------------- | ------------------------------------------------------------------------------- |
| `GET`    | `/payment-obligations`      | List obligations with search, sorting, archive filter, and currency conversion. |
| `POST`   | `/payment-obligations`      | Create a new obligation.                                                        |
| `GET`    | `/payment-obligations/{id}` | Get a single obligation by ID.                                                  |
| `PUT`    | `/payment-obligations/{id}` | Update an obligation. Only provided fields are changed.                         |
| `DELETE` | `/payment-obligations/{id}` | Delete an obligation.                                                           |

**Query parameters (list):** `search`, `sort_by` (`name`, `amount`, `currency`, `next_due_date`, `recurrence`, `category`), `sort_order`, `show_archived`, `currency`.

**Obligation fields:** `name`, `amount` (> 0), `currency`, `next_due_date` (anchor for the next occurrence — recurring obligations project forward from this), `recurrence` (optional; `monthly`, `bimonthly`, `quarterly`, `annual`, or omitted for one-off), `category` (optional, free-form, max 100 chars — see "Open" section in `docs/internal/decisions.md` for the enum-vs-tag-style discussion), `payment_method` (optional), `credit_card_id` (optional), `is_active`, `notes` (optional). Responses include `converted_amount` when `currency` query param is provided.

---

## Payments Calendar

Read-only timeline that aggregates every upcoming payment for a given calendar month: subscription charges, installment cuotas, payment obligations, and credit-card due dates.

| Method | Path                 | Description                                                |
| ------ | -------------------- | ---------------------------------------------------------- |
| `GET`  | `/payments-calendar` | Aggregated calendar events for the requested month / year. |

**Required query parameters:** `year` (integer), `month` (1-12).

**Optional query parameters:** `currency` (display currency — adds `converted_amount` on each item).

**Response shape:**

\`\`\`
{
"year": 2026,
"month": 5,
"currency": "ARS" | null,
"items": [
{
"type": "subscription" | "installment" | "obligation" | "card_due",
"date": "2026-05-15",
"name": "Netflix",
"amount": "5990.00",
"currency": "ARS",
"converted_amount": "5990.00" | null,
"payment_method": "credit_card" | null,
"credit_card_id": 12 | null,
"source_id": 7,
"cuota_index": null, // installments only
"installments_count": null, // installments only
"recurrence": null // obligations only
}
]
}
\`\`\`

`items` is sorted by date ascending. Within the same date the order is stable: `card_due` → `subscription` → `installment` → `obligation`. Card-due events emit one entry per active card per bucket with non-zero balance, dated on that month's resolved `due_day` (clamped for short months).

---

## Finance Metrics

Dashboard-oriented endpoints for income, expense, and cash flow metrics. All support `currency` conversion and optional date range filtering.

| Method | Path                                 | Description                                                         |
| ------ | ------------------------------------ | ------------------------------------------------------------------- |
| `GET`  | `/finance-metrics/overview`          | Overview: total income, expenses, net, card balance, period change. |
| `GET`  | `/finance-metrics/monthly`           | Monthly income vs expenses series (bar chart data).                 |
| `GET`  | `/finance-metrics/expense-breakdown` | Expense totals grouped by category (donut chart data).              |
| `GET`  | `/finance-metrics/income-breakdown`  | Income totals grouped by category (donut chart data).               |

**Common query parameters:** `currency` (display currency), `date_from` (start date), `date_to` (end date).

**Overview response:** `total_income`, `total_expenses`, `net`, `income_change_pct` (vs previous period), `expense_change_pct`, `credit_card_balance`.

**Monthly response:** `points[]` with `date`, `income`, `expenses` per month.

**Breakdown responses:** `items[]` with `category`, `value`, `percentage`. Multi-currency entries are converted to the display currency via USD pivot.

---

## General Dashboard

Aggregated endpoints combining investment portfolio and finance data for the home dashboard. All support optional `currency` conversion.

| Method | Path                     | Description                                                                           |
| ------ | ------------------------ | ------------------------------------------------------------------------------------- |
| `GET`  | `/dashboard/overview`    | Net worth, investment KPIs, finance KPIs, savings rate, income/expense ratio.         |
| `GET`  | `/dashboard/evolution`   | Monthly net worth series (investment value - cumulative card balance at each month).  |
| `GET`  | `/dashboard/composition` | Investment allocation by category plus a liabilities segment for credit card balance. |

**Query parameters (overview + evolution):** `currency`, `date_from` (YYYY-MM-DD), `date_to` (YYYY-MM-DD).

**Query parameters (composition):** `currency` only (no date filtering — shows current allocation).

**Overview response:** `net_worth`, `net_worth_change`, `net_worth_change_pct`, `investment_total`, `investment_gain`, `investment_gain_pct`, `investment_month_change`, `investment_month_change_pct`, `credit_card_balance`, `total_income`, `total_expenses`, `savings_rate` (null when no income), `income_expense_ratio` (null when no expenses).

**Evolution response:** `points[]` with `date`, `investment_value`, `card_balance`, `net_worth` per month.

**Composition response:** `items[]` with `label` (category name or "liabilities"), `value`, `percentage`. Plus `total_assets`, `total_liabilities`.

**Net worth formula:** `investment_total - credit_card_balance`. Cash accounts deferred — net worth currently excludes liquid cash.

---

## API Keys

API keys provide long-lived authentication for external tools (e.g., iOS Shortcuts). The raw key is shown only once at creation -- store it securely.

| Method   | Path             | Description                                               |
| -------- | ---------------- | --------------------------------------------------------- |
| `GET`    | `/api-keys`      | List all active API keys for the current user.            |
| `POST`   | `/api-keys`      | Generate a new API key. Returns the raw key (shown once). |
| `DELETE` | `/api-keys/{id}` | Revoke an API key (soft-delete).                          |

**Authentication with API keys:** Include the raw key as a Bearer token in the `Authorization` header, the same way you would with a JWT. The server tries JWT validation first, then falls back to API key verification. Currently only `POST /expenses` accepts API key auth (for iOS Shortcut expense entry).

---

## Settings

User preferences stored as key-value pairs. All fields are optional on update -- only send what you want to change.

| Method | Path        | Description                                                          |
| ------ | ----------- | -------------------------------------------------------------------- |
| `GET`  | `/settings` | Get current user's settings. **Supports both JWT and API key auth.** |
| `PUT`  | `/settings` | Update settings. Partial update -- only provided fields are changed. |

**Settings fields:**

| Field                    | Type     | Description                                                             |
| ------------------------ | -------- | ----------------------------------------------------------------------- |
| `primary_currency`       | string   | Main display currency (e.g., `USD`).                                    |
| `secondary_currency`     | string   | Secondary display currency (e.g., `ARS`).                               |
| `preferred_currencies`   | string[] | Ordered list of currencies for the currency switcher.                   |
| `period_presets`         | object[] | Custom period presets for the dashboard date range selector.            |
| `max_groups`             | int      | Maximum number of groups the user can create.                           |
| `group_warning_pct`      | number   | Percentage threshold that triggers a group allocation warning.          |
| `dollar_rate_preference` | string   | Which USD/ARS rate to use for conversions: `oficial`, `mep`, or `blue`. |
| `shortcut_currencies`    | string[] | Currencies shown in the iOS Shortcut currency picker.                   |

---

## Metrics

All metric endpoints support currency conversion via the `currency` query parameter. Pass `currency=ARS` to see values in Argentine pesos, `currency=USD` for US dollars, etc. Omit it to see values in each investment's original currency.

Most endpoints also accept these common filters:

| Parameter        | Type   | Description                           |
| ---------------- | ------ | ------------------------------------- |
| `currency`       | string | Display currency for conversion.      |
| `investment_ids` | int[]  | Limit to specific investments.        |
| `group_ids`      | int[]  | Limit to investments in these groups. |
| `category`       | string | Limit to a specific category.         |
| `search`         | string | Filter by investment name.            |
| `start_date`     | date   | Start of date range (YYYY-MM-DD).     |
| `end_date`       | date   | End of date range (YYYY-MM-DD).       |

| Method | Path                           | Description                                                                                           | Supports date range       |
| ------ | ------------------------------ | ----------------------------------------------------------------------------------------------------- | ------------------------- |
| `GET`  | `/metrics/portfolio`           | Portfolio-level metrics: total value, invested capital, gain/loss, TWR, IRR, month-over-month change. | Yes                       |
| `GET`  | `/metrics/portfolio/evolution` | Monthly portfolio value series for the evolution chart.                                               | Yes                       |
| `GET`  | `/metrics/investment/{id}`     | Detailed metrics for a single investment: TWR, IRR, period returns.                                   | No (uses `currency` only) |
| `GET`  | `/metrics/allocation`          | Portfolio allocation by investment category (percentage breakdown).                                   | No                        |
| `GET`  | `/metrics/allocation/by-group` | Portfolio allocation by group (percentage breakdown).                                                 | No                        |
| `GET`  | `/metrics/investments/summary` | Compact per-investment metrics for the dashboard table: value, return, change.                        | Yes                       |

---

## Exchange Rates

| Method | Path                     | Description                                                              |
| ------ | ------------------------ | ------------------------------------------------------------------------ |
| `GET`  | `/exchange-rates/latest` | Latest available rate for each currency pair.                            |
| `GET`  | `/exchange-rates`        | Rates for a specific date. Requires `date` query parameter (YYYY-MM-DD). |

**Available pairs:** USD/ARS (oficial), USD/ARS (MEP), USD/ARS (blue), USD/BRL, USD/EUR, USD/GBP.

---

## Asset Prices

| Method | Path                            | Description                                                                                   |
| ------ | ------------------------------- | --------------------------------------------------------------------------------------------- |
| `GET`  | `/asset-prices/{ticker}`        | Price history for a ticker. Optional: `start_date`, `end_date`.                               |
| `GET`  | `/asset-prices/{ticker}/latest` | Latest stored price for a ticker.                                                             |
| `GET`  | `/asset-prices/{ticker}/lookup` | Price for a ticker on a specific date. Fetches from the provider if not already stored.       |
| `POST` | `/asset-prices/refresh`         | Trigger an on-demand price refresh for all ticker-linked investments. Returns 202 (accepted). |

**Lookup query parameters:** `date` (required), `category` (required -- determines which provider to use), `convert_to` (optional -- target currency for price conversion).

---

## Error codes

| Code  | Meaning                                                                                                 |
| ----- | ------------------------------------------------------------------------------------------------------- |
| `401` | Unauthorized -- missing or invalid token.                                                               |
| `404` | Not found -- the resource doesn't exist or doesn't belong to you.                                       |
| `409` | Conflict -- e.g., trying to change an investment's currency when it already has snapshots.              |
| `422` | Validation error -- the request body is malformed or missing required fields.                           |
| `503` | Service unavailable -- an external service (exchange rates, price provider) is temporarily unreachable. |
