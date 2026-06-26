# Renly API Reference

All endpoints require authentication via a Bearer token (JWT) in the `Authorization` header, except for the pre-auth endpoints under `/auth` (register, login, email verification, and password reset). Some endpoints also accept API key authentication (see API Keys section).

Base URL: `/api` (all paths below are relative to this).

---

## Authentication

| Method | Path                         | Description                                                                                                                                                           |
| ------ | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST` | `/auth/register`             | Create a new account. Always returns a uniform `202`; a verification email is sent.                                                                                   |
| `POST` | `/auth/login`                | Sign in with email and password. Returns an access token + a refresh token. `remember_me: true` makes the session long-lived. `403` if the email is not yet verified. |
| `POST` | `/auth/refresh`              | Exchange a refresh token for a new access token (and a rotated refresh token). Body: `{ refresh_token }`. `401` if it is expired, revoked, or reused.                 |
| `POST` | `/auth/logout`               | Sign out. Invalidates all existing tokens for the user.                                                                                                               |
| `GET`  | `/auth/me`                   | Returns the current authenticated user (id, name, email, plan, email_verified).                                                                                       |
| `POST` | `/auth/verify-email/request` | (Re)send the email-verification link. Uniform `202`.                                                                                                                  |
| `POST` | `/auth/verify-email/confirm` | Confirm a verification or email-change token. Body: `{ token }`.                                                                                                      |
| `POST` | `/auth/forgot-password`      | Send a password-reset link. Uniform `202`.                                                                                                                            |
| `POST` | `/auth/reset-password`       | Set a new password from a reset token. Body: `{ token, password }`. Kills sessions.                                                                                   |

### Account self-service (`/me`)

Authenticated; each sensitive action re-verifies the current password.

| Method   | Path                  | Description                                                                                |
| -------- | --------------------- | ------------------------------------------------------------------------------------------ |
| `POST`   | `/me/change-password` | Change the password (verifies current). Bumps the session epoch.                           |
| `POST`   | `/me/change-email`    | Request an email change; emails a confirmation link to the new address. Uniform `202`.     |
| `GET`    | `/me/export`          | Download the user's full data set as a JSON file. Excludes password and API-key secrets.   |
| `DELETE` | `/me`                 | Permanently delete the account. Body: `{ password, confirmation }` (confirmation = email). |

Registration requires a valid email address and a password of at least 12 characters that has not appeared in a known public data breach. Emails are case-insensitive (`Foo@x.com` and `foo@x.com` are the same account). To protect privacy, registration, verification, password-reset, and email-change requests all return a **uniform response** that never reveals whether an email already has an account — the relevant message is emailed to the address instead. A new account must verify its email (via the emailed link) before it can log in.

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

## Import

Bulk-import data from a spreadsheet (CSV, TSV, or XLSX) instead of entering rows one at a time. The flow is two steps: **preview** (a dry run that maps your columns to Renly fields and validates every row, writing nothing) and **confirm** (re-validates server-side and inserts the importable rows). `{entity}` is the data type to import — currently `investments`.

Both endpoints take a `multipart/form-data` body. A single file is capped at 1,000 rows, and imports are rate-limited per user.

| Method | Path                        | Description                                                                                                                                                                                                                                                          |
| ------ | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST` | `/imports/{entity}/preview` | Dry-run preview. Form fields: `file` (required), `mapping` (optional JSON of field→column). Returns detected columns, the applied mapping, target fields, a per-row validation outcome (`valid` / `duplicate` / `invalid` + reasons), and summary counts. No writes. |
| `POST` | `/imports/{entity}`         | Re-validate the file and bulk-insert. Form fields: `file` (required), `mapping` (required JSON), `import_duplicates` (optional bool). Returns `{ created, skipped_invalid, skipped_duplicate }`.                                                                     |

**Column mapping:** the server auto-detects a sensible field→column mapping from the header row (English and Spanish header names are recognized). You can override it by passing a `mapping` JSON object (e.g. `{"name": "Investment", "base_currency": "Currency"}`); unmapped optional fields are simply left empty.

**Validation & dedup:** each row is coerced and validated against the entity's field rules (e.g. a recognized category, a supported currency, length limits). Rows that match an existing record — or an earlier row in the same file — by name (case-insensitive) are flagged as `duplicate` and skipped unless `import_duplicates` is `true`. Invalid rows are always skipped; the rest are inserted. An unreadable or unsupported file returns `400`.

**Investments fields:** `name` (required), `category` (required), `base_currency` (required), `ticker`, `broker`, `notes`.

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

| Method   | Path                          | Description                                                                         |
| -------- | ----------------------------- | ----------------------------------------------------------------------------------- |
| `GET`    | `/expenses`                   | List expenses with filtering, search, and pagination.                               |
| `POST`   | `/expenses`                   | Create a new expense. **Supports both JWT and API key auth.**                       |
| `GET`    | `/expenses/{id}`              | Get a single expense by ID.                                                         |
| `PUT`    | `/expenses/{id}`              | Update an expense. Only provided fields are changed.                                |
| `DELETE` | `/expenses/{id}`              | Delete an expense.                                                                  |
| `GET`    | `/expenses/auto-charge-match` | Look up a likely-duplicate auto-generated expense for a manual entry being drafted. |

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

**Source:** The `source` field indicates how the expense was created: `manual` (default, web app), `shortcut` (iOS Shortcut), `auto`, `email_parsed`, `subscription`, `installment`, or `reconciliation`. Sent in the request body on `POST /expenses`; returned in all responses.

**Payment obligation link:** `POST /expenses` accepts an optional `payment_obligation_id` (nullable). When set, the server (a) inserts the expense with the FK and (b) auto-advances the linked obligation in the same transaction — recurring obligations move `next_due_date` forward by one cycle (anchor-day preserved via `add_months_anchored`); one-off obligations flip `is_active=false`. The FK is also editable on `PUT /expenses/{id}` via JSON Merge Patch semantics (omit = unchanged, explicit `null` = clear). The FK is returned by `GET /expenses/{id}` and the list response. **Symmetric edit model (Phase 3, follow-up Items 10 + audit round 2):** PUT detects per-FK transitions and fires the corresponding plan helpers atomically — `X → null` (clear) reverses the OLD obligation IF this expense was its most-recent linked; `null → Y` (add) advances the NEW obligation; `X → Y` (swap, same type or cross-type) fires reverse on X AND advance on Y. **Reverse advance on delete:** if the deleted expense is the most-recent linked for its obligation, the server walks `next_due_date` back one recurrence cycle (recurring) or re-activates the row (one-off) atomically with the delete. Middle-of-chain deletions leave the cursor alone.

**Subscription / installment link:** `POST /expenses` also accepts optional `subscription_id` and `installment_id` (both nullable, mutually exclusive with `payment_obligation_id`). At most one of the three FKs may be set on the same row — an expense pays exactly one commitment-type. The same JSON Merge Patch convention applies on `PUT /expenses/{id}`: omit a key to leave the link untouched, send `null` to clear it. **Advance rule (Phase 3, follow-up Item 9, Option C):** when a manual entry's closest cycle equals the current cursor (`closest == next_billing_date` for subscriptions / `idx == current_installment` for installments), the server advances the cursor one step. When the closest cycle is _ahead_ of the cursor (pre-pay / mis-click — `multi_jump`), the link is saved but the cursor stays put; the scheduler's existing back-fill loop + the partial UNIQUE INDEX dedup handle catch-up naturally so intermediate cycles still get expense rows. Back-dated entries also never advance. **Reverse advance (Phase 3, follow-up Item 10):** symmetric to obligations — deleting or unlinking the most-recent linked expense walks the cursor back one cycle / cuota and re-activates fully-paid installments when the reverse moves the cursor back inside the cuota grid. The matching window is implicit in the closest-cycle math: an entry advances when it is closer to the current cursor than to either neighbouring cycle — effectively a half-cycle band on each side (~15 days for monthly, ~3 for weekly, ~45 for quarterly, ~6 months for annual).

**Pre-pay multiple cycles (Phase 3, follow-up Item 2):** `POST /expenses` accepts an optional `cycles_to_advance: int` (default `1`, min `1`, max `12`). When `> 1` the server inserts that many expense rows atomically — all sharing the same `date`, `amount`, `currency`, `category`, `payment_method`, `credit_card_id`, and `payment_obligation_id` — and walks `next_due_date` forward by the corresponding number of recurrence cycles in the same transaction. `cycles_to_advance > 1` requires `payment_obligation_id` to be set (returns 422 from the schema validator otherwise) and the obligation must be recurring (returns 400 from the service otherwise). The response carries the **last** inserted expense, with `advance_change.previous_cursor` set to the obligation's cursor _before_ the loop and `advance_change.new_cursor` set to its final position _after_ the N-th advance. Use case: pre-paying several cycles of a recurring obligation in one Mark Paid click without N separate clicks.

**Mutation response — symmetric cursor changes (Phase 3, follow-up Item 7 + audit round 2):** `POST /expenses` and `PUT /expenses/{id}` return the saved expense with two optional fields, `advance_change` and `reverse_change`. `POST` populates `advance_change` when a linked FK triggered an advance (Mark Paid / create with FK). `PUT` can populate either field independently OR both simultaneously: a FK swap fires reverse on the OLD plan AND advance on the NEW plan in the same transaction. `DELETE /expenses/{id}` returns `{ "reverse_change": ... }` (was `204 No Content` before Item 10; delete never advances). Each cursor-change shape: `{ plan_type, plan_id, plan_name, previous_cursor, new_cursor, total_count }`. `plan_type` is one of `"obligation" | "subscription" | "installment"`; `previous_cursor` and `new_cursor` are stringified — ISO date for obligation/subscription, decimal index for installment; `new_cursor` is empty when the plan archived (one-off obligation Marked Paid, installment past its final cuota), `previous_cursor` is empty when the plan re-activated via reverse. `total_count` is the installment plan's `installments_count` (used by the client to render "cuota N of M" without an extra lookup) and is `null` for obligations and subscriptions.

**Amount validation:** `amount` must be greater than zero on all create and update endpoints (expenses, income, settlements). Returns 422 if zero or negative.

**Currency conversion:** When `currency` is provided, the response includes `converted_amount` per entry and `display_currency` on the list response. The original `amount` and `currency` are always preserved.

### Auto-charge match (Phase 3, Step D)

`GET /expenses/auto-charge-match` is a lookup endpoint the expense form calls before submitting a new manual credit-card expense, to warn the user when they're about to enter a row that matches an already-scheduler-generated charge.

**Query parameters:** `credit_card_id` (int, required), `currency` (string, required), `amount` (decimal, required), `date` (YYYY-MM-DD, required), `exclude_expense_id` (int, optional — set on the edit flow so the row being edited doesn't match itself).

**Match rule:** existing `expense_entries` with `source IN ('subscription', 'installment')` AND same `credit_card_id` AND same `currency` AND exact `amount` match AND `date` within ±15 days of the supplied `date`. When `exclude_expense_id` is set, that row is excluded from the result. Newest match wins; only the first match is returned.

**Response:** `{ "match": null }` when no row matches; otherwise `{ "match": { "expense_id", "date", "source": "subscription" | "installment", "source_plan": { "id", "name" } } }`. The `source_plan.name` is the subscription / installment name for display in the confirmation dialog.

### Cycle-advance preview (Phase 3, follow-up 3b)

`GET /expenses/cycle-advance-preview` is a lookup endpoint the expense form calls before submitting a manual entry linked to a subscription or installment, to decide whether the plan's cursor will advance on save. When the cursor won't advance, the form shows a soft-confirm dialog so the user understands the FK still saves but the schedule stays put.

**Query parameters:** `entry_date` (YYYY-MM-DD, required), `subscription_id` (int, optional), `installment_id` (int, optional). Exactly one of `subscription_id` / `installment_id` must be set; supplying neither or both returns 400.

**Decision rule:** finds the closest cycle to `entry_date` (subscription: walks forward/backward by `billing_cycle` from `next_billing_date`; installment: clamps to `[1, installments_count]` around `start_date + (idx - 1) months`). Advance fires only when the matched cycle equals the current cursor (`closest == next_billing_date` for subscriptions, `idx == current_installment` for installments) — Phase 3, follow-up Item 9, Option C. The "closest" math implicitly enforces a half-cycle window around the cursor: an entry within ~half a cycle of the current cursor matches the cursor; further out, it matches a neighbour and `would_advance=false`. When the closest cycle is _ahead_ of the cursor, `multi_jump=true` (pre-pay / mis-click): the link still saves on `POST /expenses` but the cursor stays put — the scheduler back-fills intermediate cycles naturally via the partial UNIQUE INDEX dedup. Back-dated entries (`multi_jump=false` with `would_advance=false`) also never rewind the schedule. Returns 404 when the referenced plan doesn't belong to the user.

**Response:** `{ "would_advance": bool, "distance_days": int, "next_expected_date": "YYYY-MM-DD", "multi_jump": bool }`. `next_expected_date` is the closest cycle the entry was matched against (informational when `would_advance=false`). `multi_jump=true` means the matched cycle is ahead of the current cursor — used by the client to surface a different soft-confirm copy than the back-dated case.

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

**Card fields:** `name`, `closing_day` (1-31), `due_day` (1-31), `currency` (ISO 4217 — the card's primary/statement currency), `is_active` (boolean), `monthly_payment` (optional Decimal ≥ 0 — typical monthly payment for revolving-debt users; counts as a fixed commitment on the dashboard Liquidity card when set; null = pay-in-full, excluded from the ratio), `has_expenses` (computed, read-only), `balances` (computed — list of `{currency, balance}` per currency with activity; primary always present, others added by expense activity in non-primary currencies; balances are NOT converted across currencies).

**Archive behavior:** Archived cards are hidden from the expense form's card selector but retain all linked expenses and settlements. Bucket balances are still computed normally. Delete is only allowed when the card has no linked expenses (409 otherwise).

**Settlement fields:** `date`, `amount`, `currency` (required — selects which bucket the settlement reduces), `notes` (optional). Settlements have no statement-period link; per-statement amounts are derived as running-balance snapshots at the period's closing date.

### Card Reconciliations (Phase 3, Step 5)

Per-bucket, per-statement true-up against the bank. Captures fees / FX / taxes / timing that fall outside the app's normal model. See [Credit Card Liability Model](../technical/credit-card-liability-model.md) for the full math.

| Method   | Path                                       | Description                                                                                                                                                               |
| -------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`    | `/credit-cards/{id}/reconciliations`       | List reconciliations for a card. Optional `currency` filter selects a single bucket.                                                                                      |
| `GET`    | `/credit-cards/{id}/statements`            | List recent statement periods per bucket with `Reconciled` / `Not reconciled` / `Stale` status. Drives the Reconciliations sub-section UI.                                |
| `POST`   | `/credit-cards/{id}/reconciliations`       | Create-or-replace a reconciliation. If one exists for the same `(currency, period_start, period_end)`, it (and its adjustment) is deleted before the new pair is written. |
| `DELETE` | `/credit-cards/{id}/reconciliations/{rid}` | Delete a reconciliation. Cascade-deletes its adjustment expense or income.                                                                                                |

**`POST` body:** `currency`, `period_start`, `period_end`, `statement_balance`. The server computes `computed_balance` (= running balance at `period_end` for the bucket), `difference = statement_balance − computed_balance`, and creates a matching adjustment: an `expense_entries` row (category `card_fees_and_taxes`, `source='reconciliation'`) when `difference > 0`, an `income_entries` row (category `card_credits_and_refunds`, `source='reconciliation'`) when `difference < 0`, none when `difference == 0`. The adjustment is dated on `period_end` so it flows naturally into the next period's running balance.

**Reconciliation fields:** `id`, `card_id`, `currency`, `period_start`, `period_end`, `statement_balance`, `computed_balance`, `difference`, `adjustment_expense_id`, `adjustment_income_id`, `is_stale` (flipped to `true` when a relevant expense or settlement is created / edited / deleted inside the period after this reconciliation), `reconciled_at`.

**Statement-period semantics:** A statement is identified by its closing date. The period spans `(prev_closing_date, this_closing_date]` — the closing date is the LAST day of the statement it closes; the next statement starts the day after. Day-of-month overflow (e.g. `closing_day = 31` in February) is resolved by clamping to the last day of the target month.

**Uniqueness:** `(card_id, currency, period_start, period_end)`. `POST` always behaves as create-or-replace.

---

## Subscriptions

Recurring charges (e.g. Netflix, Spotify, gym). The daily scheduler auto-generates one expense entry per billing cycle, advances `next_billing_date`, and back-fills missed cycles for subscriptions registered with a past `next_billing_date`.

| Method   | Path                  | Description                                                                       |
| -------- | --------------------- | --------------------------------------------------------------------------------- |
| `GET`    | `/subscriptions`      | List subscriptions with search, sorting, archive filter, and currency conversion. |
| `POST`   | `/subscriptions`      | Create a new subscription. **Supports both JWT and API key auth.**                |
| `GET`    | `/subscriptions/{id}` | Get a single subscription by ID.                                                  |
| `PUT`    | `/subscriptions/{id}` | Update a subscription. Only provided fields are changed.                          |
| `DELETE` | `/subscriptions/{id}` | Delete a subscription.                                                            |

**Query parameters (list):** `search`, `sort_by` (`name`, `amount`, `currency`, `billing_cycle`, `next_billing_date`), `sort_order` (`asc`/`desc`), `show_archived`, `include_ids` (repeated archived subscription ids to surface alongside the active set — used by the expense edit dialog so a row linked to a since-archived subscription still resolves to the plan name; ignored when `show_archived=true`), `currency` (display currency for conversion).

**Subscription fields:** `name`, `amount` (> 0), `currency` (ISO 4217), `billing_cycle` (`monthly`, `annual`, `quarterly`, `biweekly`, `weekly`), `payment_method` (optional; `cash`, `debit`, `transfer`, `credit_card`), `credit_card_id` (when payment_method = credit_card), `is_active`, `next_billing_date`. Responses also include `converted_amount` when `currency` query param is provided.

---

## Installments

Cuotas (installment plans, e.g. TV Samsung 12x). The daily scheduler auto-generates one expense entry per cuota and back-fills missed cuotas for plans registered with a past `start_date`.

| Method   | Path                 | Description                                                                           |
| -------- | -------------------- | ------------------------------------------------------------------------------------- |
| `GET`    | `/installments`      | List installment plans with search, sorting, archive filter, and currency conversion. |
| `POST`   | `/installments`      | Create a new installment plan. **Supports both JWT and API key auth.**                |
| `GET`    | `/installments/{id}` | Get a single installment plan by ID.                                                  |
| `PUT`    | `/installments/{id}` | Update an installment plan. Only provided fields are changed.                         |
| `DELETE` | `/installments/{id}` | Delete an installment plan.                                                           |

**Query parameters (list):** `search`, `sort_by` (`name`, `total_amount`, `installment_amount`, `currency`, `installments_count`, `current_installment`, `start_date`, `next_cuota_date`), `sort_order`, `show_archived`, `include_ids` (repeated archived plan ids to surface alongside the active set — used by the expense edit dialog so a row linked to a since-archived plan still resolves to the plan name; ignored when `show_archived=true`), `currency`. Default order is `next_cuota_date DESC` so the table leads with the plan due next.

**Installment fields:** `name`, `total_amount` (> 0), `installment_amount` (> 0), `currency`, `installments_count` (≥ 1), `current_installment` (≥ 1; default 1), `payment_method` (optional), `credit_card_id` (optional), `is_active`, `start_date`. Responses also include `next_cuota_date` (computed = `start_date + (current_installment - 1) months` with month-end clamping; `null` once the plan is fully paid) and `converted_total_amount` / `converted_installment_amount` when `currency` query param is provided.

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

**Query parameters (list):** `search`, `sort_by` (`name`, `amount`, `currency`, `next_due_date`, `recurrence`, `category`), `sort_order`, `show_archived`, `include_ids` (repeated archived obligation ids to surface alongside the active set — used by the expense edit dialog so a row linked to a since-archived obligation still resolves to the obligation name; ignored when `show_archived=true`), `currency`.

**Obligation fields:** `name`, `amount` (> 0), `currency`, `next_due_date` (anchor for the next occurrence — recurring obligations project forward from this), `recurrence` (optional; `monthly`, `bimonthly`, `quarterly`, `annual`, or omitted for one-off), `category` (optional, free-form user label, max 100 chars — e.g. "ABL", "Cable"), `expense_category` (optional, structured enum reusing `ExpenseCategory` — used to pre-fill Mark Paid + feed finance breakdowns), `payment_method` (optional), `credit_card_id` (optional), `is_active`, `notes` (optional), `last_payment_date` (computed, read-only — date of the most recent linked expense, surfaces on archived one-off rows as a "Paid on" indicator). Responses include `converted_amount` when `currency` query param is provided.

**Paid state (Phase 3, Step E):** Obligations are paid by creating a linked expense from the "Mark paid" action on the obligations table. The expense form opens pre-filled from the obligation, and on save `POST /expenses` carries `payment_obligation_id` — the obligation's `next_due_date` auto-advances one cycle (recurring) or `is_active` flips to `false` (one-off) atomically with the expense insert. The advance is one-way: editing or deleting a linked expense does NOT reverse it. To correct an over-advance, `PUT /payment-obligations/{id}` with the desired `next_due_date`.

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
"recurrence": null, // obligations only
"is_paid": false, // obligation / subscription / installment past cycles whose scheduler-emitted or linked expense exists
"linked_expense_id": null // set on past-paid items; lets the frontend open the linked expense's edit dialog inline
}
]
}
\`\`\`

`items` is sorted by date ascending. Within the same date the order is stable: `card_due` → `subscription` → `installment` → `obligation`. Card-due events emit one entry per active card per bucket, dated on that month's resolved `due_day` (clamped for short months); the amount is the bucket's **running balance at the statement's closing date** (= `sum(expenses dated ≤ closing_date) − sum(settlements dated ≤ closing_date)` for that bucket). Carryover from prior unpaid statements is implicit in the snapshot, matching how a real bank resumen presents the bill. Buckets whose snapshot is zero are omitted. When a reconciliation exists for the period, the reconciliation's adjustment is part of the running balance via its dated adjustment entry.

**Obligation projection (Phase 3, Step E):** Obligations project both forward AND backward from `next_due_date` so the calendar shows BOTH unpaid future cycles (the existing behaviour) AND past-paid cycles whose period contains a linked expense. Past-paid cycles carry `is_paid = true`; unpaid future cycles carry `is_paid = false`. The walker uses `add_months_anchored` so anchor day is preserved across short-month clamps. A backward-walked occurrence at date `D` is paid when an expense with `payment_obligation_id = obligation.id` has its date inside the occurrence's cycle period `(prev_anchor, D]`.

**Subscription / installment projection (Phase 3 follow-up):** Symmetric to obligations. Forward walker emits unpaid future cycles (subscription billing cycles from `next_billing_date`; installment cuotas from `current_installment` to `installments_count`). Backward walker emits past PAID cycles whose scheduler-emitted expense row exists, matched via the partial UNIQUE INDEX on `(subscription_id, date)` / `(installment_id, date)`. Past-paid items use the linked expense's historical amount + currency.

**`linked_expense_id` field:** Set on past-paid items of any type (obligation, subscription, installment); always null on `card_due` and future unpaid cycles. Frontend uses it to open the linked expense's edit dialog inline when the user clicks the Paid badge — no page navigation.

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

| Method | Path                     | Description                                                                                                |
| ------ | ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `GET`  | `/dashboard/overview`    | Net worth, investment KPIs, finance KPIs, savings rate, income/expense ratio.                              |
| `GET`  | `/dashboard/evolution`   | Monthly net worth series (investment value - cumulative card balance at each month).                       |
| `GET`  | `/dashboard/composition` | Investment allocation by category plus a liabilities segment for credit card balance.                      |
| `GET`  | `/dashboard/liquidity`   | Liquidity health indicator: fixed monthly commitments / monthly income ratio classified against threshold. |

**Query parameters (overview + evolution):** `currency`, `date_from` (YYYY-MM-DD), `date_to` (YYYY-MM-DD).

**Query parameters (composition + liquidity):** `currency` only (no date filtering — shows current snapshot).

**Overview response:** `net_worth`, `net_worth_change`, `net_worth_change_pct`, `investment_total`, `investment_gain`, `investment_gain_pct`, `investment_month_change`, `investment_month_change_pct`, `credit_card_balance`, `total_income`, `total_expenses`, `savings_rate` (null when no income), `income_expense_ratio` (null when no expenses).

**Evolution response:** `points[]` with `date`, `investment_value`, `card_balance`, `net_worth` per month.

**Composition response:** `items[]` with `label` (category name or "liabilities"), `value`, `percentage`. Plus `total_assets`, `total_liabilities`.

**Liquidity response:** `ratio` (null when income is zero or history too short), `state` (`healthy` / `caution` / `at_risk` / `unknown`), `fixed_monthly_commitments`, `monthly_income`, `threshold` (integer percent), `income_window_days` (target = 90), `actual_window_days` (smaller during early app life), `currency`, `skipped_entities` (defensive diagnostic listing any commitment whose currency couldn't be converted — always empty in practice today). Commitments amortise subscriptions / installments / recurring obligations to a monthly base, plus any credit card with `monthly_payment` set (revolving-debt users); income is the user's last 90 days (or actual elapsed days, minimum 7) normalised to 30. Configure the threshold via `liquidity_threshold_pct` on settings.

**Classification bands:** `healthy` when `ratio × 100 < threshold`; `caution` when `threshold ≤ ratio × 100 < threshold + 10`; `at_risk` when `ratio × 100 ≥ threshold + 10`; `unknown` when income is zero or the user has fewer than 7 days of income history. The +10pp caution band is hardcoded.

**Net worth formula:** `investment_total - credit_card_balance`. Cash accounts deferred — net worth currently excludes liquid cash.

---

## API Keys

API keys provide long-lived authentication for external tools (e.g., iOS Shortcuts). The raw key is shown only once at creation -- store it securely.

| Method   | Path             | Description                                               |
| -------- | ---------------- | --------------------------------------------------------- |
| `GET`    | `/api-keys`      | List all active API keys for the current user.            |
| `POST`   | `/api-keys`      | Generate a new API key. Returns the raw key (shown once). |
| `DELETE` | `/api-keys/{id}` | Revoke an API key (soft-delete).                          |

**Authentication with API keys:** Include the raw key as a Bearer token in the `Authorization` header, the same way you would with a JWT. The server tries JWT validation first, then falls back to API key verification. API key auth is accepted on the endpoints the iOS Shortcut needs to drive its three logging flows: `POST /expenses`, `POST /subscriptions`, `POST /installments`, plus the read-only `GET /credit-cards` and `GET /settings` it uses to populate pickers.

---

## Settings

User preferences stored as key-value pairs. All fields are optional on update -- only send what you want to change.

| Method | Path        | Description                                                          |
| ------ | ----------- | -------------------------------------------------------------------- |
| `GET`  | `/settings` | Get current user's settings. **Supports both JWT and API key auth.** |
| `PUT`  | `/settings` | Update settings. Partial update -- only provided fields are changed. |

**Settings fields:**

| Field                          | Type     | Description                                                                                                                                                                                                                         |
| ------------------------------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `primary_currency`             | string   | Main display currency (e.g., `USD`).                                                                                                                                                                                                |
| `secondary_currency`           | string   | Secondary display currency (e.g., `ARS`).                                                                                                                                                                                           |
| `preferred_currencies`         | string[] | Ordered list of currencies for the currency switcher.                                                                                                                                                                               |
| `period_presets`               | object[] | Custom period presets for the dashboard date range selector.                                                                                                                                                                        |
| `max_groups`                   | int      | Maximum number of groups the user can create.                                                                                                                                                                                       |
| `group_warning_pct`            | number   | Percentage threshold that triggers a group allocation warning.                                                                                                                                                                      |
| `dollar_rate_preference`       | string   | Which USD/ARS rate to use for conversions: `oficial`, `mep`, or `blue`.                                                                                                                                                             |
| `shortcut_currencies`          | string[] | Currencies shown in the iOS Shortcut currency picker.                                                                                                                                                                               |
| `timezone`                     | string   | User's IANA timezone (e.g. `America/Argentina/Buenos_Aires`). Used by the auto-expense scheduler to fire cycles on the user's local calendar day. Defaults to UTC when unset. Validated server-side; invalid IANA names return 400. |
| `timezone_mode`                | string   | `auto` or `manual`. In `auto`, the browser-detected timezone is silently kept in sync on every protected page load. In `manual`, the stored value never changes automatically.                                                      |
| `language`                     | string   | User's preferred language code (`en` or `es`). Drives next-intl message loading.                                                                                                                                                    |
| `language_mode`                | string   | `auto` or `manual` — same semantics as `timezone_mode` but for language.                                                                                                                                                            |
| `liquidity_threshold_pct`      | int      | Liquidity-alert threshold as integer percent (1–99). Drives the `/dashboard/liquidity` state classification. Null falls back to the backend default (`40`).                                                                         |
| `savings_rate_healthy_pct`     | int      | Savings rate at or above this percent renders the Savings Rate dashboard card green. Default 20 when null.                                                                                                                          |
| `savings_rate_moderate_pct`    | int      | Savings rate below healthy but at or above this renders amber. Below this renders red. Default 10 when null.                                                                                                                        |
| `income_expense_ratio_healthy` | Decimal  | Income/expense ratio at or above this renders the Income/Expense dashboard card green. Break-even (1.0) is the amber pivot. Default 1.5 when null. Range `[0.1, 10.0]`. Stored as string in JSONB to preserve precision.            |

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

| Method | Path                            | Description                                                                                        |
| ------ | ------------------------------- | -------------------------------------------------------------------------------------------------- |
| `GET`  | `/asset-prices/{ticker}`        | Price history for a ticker. Optional: `start_date`, `end_date`.                                    |
| `GET`  | `/asset-prices/{ticker}/latest` | Latest stored price for a ticker.                                                                  |
| `GET`  | `/asset-prices/{ticker}/lookup` | Price for a ticker on a specific date. Fetches from the provider if not already stored.            |
| `POST` | `/asset-prices/refresh`         | Trigger an on-demand price refresh for your own ticker-linked investments. Returns 202 (accepted). |

**Lookup query parameters:** `date` (required), `category` (required -- determines which provider to use), `convert_to` (optional -- target currency for price conversion).

---

## Error codes

| Code  | Meaning                                                                                                                                                                                                                                                                  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `401` | Unauthorized -- missing or invalid token.                                                                                                                                                                                                                                |
| `404` | Not found -- the resource doesn't exist or doesn't belong to you.                                                                                                                                                                                                        |
| `409` | Conflict -- e.g., trying to change an investment's currency when it already has snapshots, or a partial UNIQUE INDEX rejection on the expense entries table (manual entry duplicating a scheduler-emitted row for the same subscription / installment on the same date). |
| `422` | Validation error -- the request body is malformed or missing required fields.                                                                                                                                                                                            |
| `503` | Service unavailable -- an external service (exchange rates, price provider) is temporarily unreachable.                                                                                                                                                                  |
