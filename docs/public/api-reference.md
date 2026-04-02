# Renly API Reference

All endpoints require authentication via a Bearer token (JWT) in the `Authorization` header, except for `POST /auth/register` and `POST /auth/login`.

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

Groups are user-defined labels for organizing investments (e.g., "Retirement", "Trading", "Kids"). An investment can belong to multiple groups.

| Method   | Path                       | Description                                                                        |
| -------- | -------------------------- | ---------------------------------------------------------------------------------- |
| `GET`    | `/groups`                  | List all groups. Each group includes its investment IDs.                           |
| `POST`   | `/groups`                  | Create a new group.                                                                |
| `GET`    | `/groups/{id}`             | Get a single group with its investment IDs.                                        |
| `PUT`    | `/groups/{id}`             | Update a group (e.g., rename it).                                                  |
| `DELETE` | `/groups/{id}`             | Delete a group.                                                                    |
| `PUT`    | `/groups/{id}/investments` | Replace the group's investment membership. Body: `{ investment_ids: [5, 12, 8] }`. |

**List query parameters:** `search` (filter by name), `sort_by` (`name`), `sort_order` (`asc`/`desc`).

---

## Settings

User preferences stored as key-value pairs. All fields are optional on update -- only send what you want to change.

| Method | Path        | Description                                                          |
| ------ | ----------- | -------------------------------------------------------------------- |
| `GET`  | `/settings` | Get current user's settings.                                         |
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
