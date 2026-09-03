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
| `GET`  | `/auth/signup-context`       | Whether signup is invite-only, and the address an invite link is bound to. Unauthenticated — the signup page calls it before showing a form.                          |

**`GET /auth/signup-context`** exists so the signup page can tell the difference between "fill in this form" and "you need an invite" before asking for anything. It returns `{ signup_mode, invited_email }`: `signup_mode` is `invite` or `open`, and `invited_email` is the address a supplied `?invite=<token>` is bound to — so the form can lock the email field to it — or `null` when signup is open or the token is unknown, expired or already used. One answer for all three failure cases, so a token cannot be probed.

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

| Method  | Path                            | Description                                                                            |
| ------- | ------------------------------- | -------------------------------------------------------------------------------------- |
| `GET`   | `/investments`                  | List investments with filtering, search, and pagination.                               |
| `POST`  | `/investments`                  | Create a new investment.                                                               |
| `GET`   | `/investments/{id}`             | Get a single investment by ID.                                                         |
| `PUT`   | `/investments/{id}`             | Update an investment. Only provided fields are changed.                                |
| `PATCH` | `/investments/{id}/archive`     | Archive an investment (hides it from the active portfolio).                            |
| `PATCH` | `/investments/{id}/unarchive`   | Restore an archived investment.                                                        |
| `PUT`   | `/investments/{id}/collections` | Replace collection membership for this investment. Body: `{ collection_ids: [1, 3] }`. |

Every investment response — list, get-by-id, create and update — carries its `collections` as `{ id, name }` objects, plus `has_snapshots`.

**List query parameters:**

| Parameter        | Type    | Default | Description                                                |
| ---------------- | ------- | ------- | ---------------------------------------------------------- |
| `search`         | string  | --      | Filter by name (case-insensitive).                         |
| `collection_ids` | int[]   | --      | Filter to investments in any of these collections.         |
| `category`       | string  | --      | Filter by category (e.g., `cedears`, `stocks`).            |
| `active_only`    | boolean | `true`  | Whether to exclude archived investments.                   |
| `page`           | int     | `1`     | Page number (1-based).                                     |
| `page_size`      | int     | `20`    | Results per page (max 100).                                |
| `sort_by`        | string  | --      | Sort field: `name`, `category`, `base_currency`, `broker`. |
| `sort_order`     | string  | `asc`   | Sort direction: `asc` or `desc`.                           |

---

## Import

Bulk-import data from a spreadsheet (CSV, TSV, or XLSX) instead of entering rows one at a time. The flow is two steps: **preview** (a dry run that maps your columns to Renly fields and validates every row, writing nothing) and **confirm** (re-validates server-side and inserts the importable rows). `{entity}` is the data type to import — currently `investments`, `expenses`, `income`, `snapshots`, or `transactions`.

Both endpoints take a `multipart/form-data` body. A single file is capped at 1,000 rows, and imports are rate-limited per user.

| Method | Path                        | Description                                                                                                                                                                                                                                                          |
| ------ | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST` | `/imports/{entity}/preview` | Dry-run preview. Form fields: `file` (required), `mapping` (optional JSON of field→column). Returns detected columns, the applied mapping, target fields, a per-row validation outcome (`valid` / `duplicate` / `invalid` + reasons), and summary counts. No writes. |
| `POST` | `/imports/{entity}`         | Re-validate the file and bulk-insert. Form fields: `file` (required), `mapping` (required JSON), `import_duplicates` (optional bool). Returns `{ created, skipped_invalid, skipped_duplicate }`.                                                                     |

**Column mapping:** the server auto-detects a sensible field→column mapping from the header row (English and Spanish header names are recognized). You can override it by passing a `mapping` JSON object (e.g. `{"name": "Investment", "base_currency": "Currency"}`); unmapped optional fields are simply left empty.

**Validation & dedup:** each row is coerced and validated against the entity's field rules (e.g. a recognized category, a supported currency, length limits, a parseable date and a positive amount). Rows that match an existing record — or an earlier row in the same file — are flagged as `duplicate` and skipped unless `import_duplicates` is `true`. The dedup key depends on the entity: investments match by `name` (case-insensitive); expenses and income (which have no natural key) match on the combination of `date`, `amount`, `currency`, `category`, and `notes`; transactions match on the resolved investment plus `date`, `type`, `amount`, `currency`, and `quantity`. **Snapshots are the exception — they upsert** (one snapshot per investment per date), so a re-import updates the existing date instead of being flagged as a duplicate. Invalid rows are always skipped; the rest are inserted. An unreadable or unsupported file returns `400`.

**Nested entities (snapshots, transactions):** these belong to an investment, so the file must include an **`investment` column** holding a name or ticker. Each row is matched to one of your investments — ticker first, then name (case-insensitive) — and the lowest (oldest) id wins if more than one matches. A row whose `investment` matches none of your investments is flagged `invalid`; investments are never created by the import. Their `currency` is limited to the supported set (`USD`, `ARS`, `BRL`, `EUR`, `GBP`).

**Dates & amounts:** dates accept ISO (`YYYY-MM-DD`) plus common locale formats — day-first (`DD/MM/YYYY`) is preferred for ambiguous values, with unambiguous US dates still parsed. Amounts accept both `1.234,56` and `1,234.56` grouping and are stored to 2 decimal places; for 2-decimal money a lone separator before three digits reads as a thousands group (`1.500` → 1500). The 6-decimal `quantity` field is different: a lone separator is always the decimal mark (`1.500` → 1.5, `0.125` → 0.125).

**Investments fields:** `name` (required), `category` (required), `base_currency` (required, supported set — `USD`/`ARS`/`BRL`/`EUR`/`GBP`), `ticker`, `broker`, `notes`.

**Expenses fields:** `date` (required), `amount` (required), `currency` (required), `category`, `payment_method`, `notes`. Imported rows are recorded with source `manual`. On import, `payment_method` also accepts common EN/ES and card-brand labels (e.g. `Efectivo`, `Débito`, `Transferencia`, `Visa`, `Mastercard`, `Tarjeta de crédito`), each mapped to a canonical value; an unrecognized value is dropped with a per-row warning (the row still imports, just without a payment method) rather than rejecting the row. Imports never attach a `credit_card_id`.

**Payment method values (all four commitment entities).** `payment_method` accepts only the canonical values `cash`, `debit`, `transfer`, `credit_card` — any other string is rejected with `422`. **Pairing rule:** `credit_card_id` may only be set when `payment_method` is `credit_card`; a `credit_card_id` paired with any other method returns `422` (create / same-request update) or `400` (an update whose merged effective method is not `credit_card`). A `credit_card` entry with **no** `credit_card_id` is allowed (zero-card users and imports). This applies identically to expenses, subscriptions, installments, and payment obligations.

**Income fields:** `date` (required), `amount` (required), `currency` (required), `category`, `notes`. Imported rows are recorded with source `manual`.

**Snapshots fields:** `investment` (required — name or ticker), `date` (required), `value` (required, `0` or greater), `currency` (required, supported set — must match the investment's `base_currency`), `quantity`, `notes`. Upserts on (investment, date). Imported rows are recorded with source `manual`.

**Transactions fields:** `investment` (required — name or ticker), `date` (required), `amount` (required), `currency` (required, supported set — must match the investment's `base_currency`), `type` (required — `buy`/`sell`/`deposit`/`withdrawal`), `quantity`, `notes`.

---

## Restore

Rebuild your data from a **Renly export** (the JSON file from `GET /me/export`) — the inverse of that export, for backups and moving between accounts. Like the import flow it is two steps: **preview** (a dry run reporting what would be inserted, writing nothing) and **confirm** (re-validates server-side and inserts). Both take a `multipart/form-data` body with a single `.json` `file` and are rate-limited per user.

- `POST /restore/preview` → `{recognized, exported_at, entities: [{entity, restore, skipped_unresolved}], skipped_entities}`
- `POST /restore` → `{restored, skipped_unresolved, entities: [...]}`

**Additive and non-destructive.** Restore only inserts — it never deletes or overwrites existing rows. It is **not** deduplicated: it does not try to detect rows you already have, so restoring the same file twice inserts everything twice. **Restore into a fresh account** (its purpose is rebuilding a lost account or migrating to a new one); the preview shows exactly how many rows will be added before you confirm.

**Foreign keys are remapped.** Exported ids won't match the target account, so parents are inserted first and each child's reference is repointed to the newly inserted id. A row whose required parent can't be resolved (or whose data is invalid) is counted under `skipped_unresolved` and skipped; everything else is inserted in one transaction.

**What is restored:** investments, collections (and memberships), snapshots, transactions, credit cards, cash/bank accounts, subscriptions, installments, payment obligations, expenses, income, card settlements, and transfers. **Not restored** (reported in `skipped_entities`): API keys (the export omits their secret), settings, and both reconciliation types. Restored expenses/income keep their amount, date, category, notes **and the cash/bank account they were linked to** — their scheduler and reconciliation links are dropped, so they arrive as plain entries. An unreadable file, one that isn't a Renly export, or one whose contents violate a constraint returns `400`.

**Balances come back on their own.** Every balance in Renly is derived, never stored: an account's is its `opening_balance` plus the rows linked to it, and a card's is its charges minus the settlements paid against it. Restoring those rows and keeping their links intact therefore reproduces both figures with no extra step.

Reconciliations are the deliberate exception. Each one is a point-in-time true-up recorded against a balance the restore has just re-derived from scratch, so replaying an old one would post a second adjustment for drift that no longer exists. **Reconcile after restoring** if a balance still doesn't match your bank or your statement.

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

| Parameter        | Type   | Default | Description                                                                       |
| ---------------- | ------ | ------- | --------------------------------------------------------------------------------- |
| `search`         | string | --      | Filter by investment name.                                                        |
| `collection_ids` | int[]  | --      | Filter by collection IDs.                                                         |
| `category`       | string | --      | Filter by category.                                                               |
| `currency`       | string | --      | Display currency for conversion (e.g., `USD`, `ARS`). Omit for original currency. |
| `sort_by`        | string | --      | Sort field: `name`.                                                               |
| `sort_order`     | string | `asc`   | Sort direction: `asc` or `desc`.                                                  |

---

## Collections

Collections are user-defined labels for organizing investments (e.g., "Retirement", "Trading", "Kids"). An investment can belong to multiple collections. Each collection can have an optional target allocation percentage for the dashboard.

| Method   | Path                            | Description                                                                   |
| -------- | ------------------------------- | ----------------------------------------------------------------------------- |
| `GET`    | `/collections`                  | List all collections. Each includes its investment IDs and target percentage. |
| `POST`   | `/collections`                  | Create a new collection. Optional: `target_percentage` (0-100).               |
| `GET`    | `/collections/{id}`             | Get a single collection with its investment IDs.                              |
| `PUT`    | `/collections/{id}`             | Update a collection. Fields: `name`, `target_percentage` (both optional).     |
| `DELETE` | `/collections/{id}`             | Delete a collection.                                                          |
| `PUT`    | `/collections/{id}/investments` | Replace the collection's membership. Body: `{ investment_ids: [5, 12, 8] }`.  |

**List query parameters:** `search` (filter by name), `sort_by` (`name`), `sort_order` (`asc`/`desc`).

**Collection allocation metrics** (`GET /metrics/allocation/by-collection`) include `target_percentage` and `difference` (actual minus target) for each collection that has a target set. Investments in no collection are bucketed under `Unassigned`.

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

**Income categories:** `salary`, `freelance`, `bonus`, `investment_returns`, `dividends`, `rental_income`, `sales`, `refunds`, `gifts`, `other`. Two further values are **reserved for the system** and are rejected with **422** on create and update: `account_adjustment` (the surplus direction of an account reconciliation) and `card_credits_and_refunds` (legacy — card credits are signed expenses now, so nothing writes it, but historical rows carry it). See the same note under [Expenses](#expenses).

**Reconciliation-owned entries are read-only.** Every income response carries `account_reconciliation_id` (the owning account reconciliation) and a legacy `reconciliation_id` (a card reconciliation; no longer written), both nullable and read-only. Exactly as on the expense side, a non-null value makes the row a reconciliation's adjustment, and `PUT /income/{id}` / `DELETE /income/{id}` are refused with **409** `reconciliation_owned_entry` — change it by re-running or deleting its reconciliation. See the same note under [Expenses](#expenses) for the full rationale.

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

**Expense categories:** `food`, `dining`, `transport`, `rent`, `utilities`, `health`, `entertainment`, `sports`, `subscriptions`, `clothing`, `education`, `personal_care`, `home_maintenance`, `gifts`, `travel`, `taxes`, `insurance`, `kids`, `pets`, `other`. Three further values are **reserved for the system** and are rejected with **422** on any create or update (`/expenses`, and `expense_category` on `/payment-obligations`): `card_fees_and_taxes` and `card_credits_and_refunds` (the two directions of a card reconciliation) and `account_adjustment` (either direction of an account reconciliation). Only a reconciliation writes them, and they appear in responses as normal. They label a true-up, which is what lets a balance correction be told apart from real spending — a user-supplied value would be indistinguishable from one the app computed. The CSV/XLSX importers don't accept them either.

**Payment methods:** `cash`, `debit`, `transfer`, `credit_card`.

**Source:** The `source` field indicates how the expense was created: `manual` (default, web app), `shortcut` (iOS Shortcut), `auto`, `email_parsed`, `subscription`, `installment`, or `reconciliation`. Sent in the request body on `POST /expenses`; returned in all responses. `source` records provenance only — it is not what makes a row read-only (see below).

**Reconciliation-owned entries are read-only.** Every expense response carries `reconciliation_id` (the owning **card** reconciliation) and `account_reconciliation_id` (the owning **account** reconciliation), both nullable and both read-only. A non-null value means the row is that reconciliation's **adjustment**: its amount IS the reconciliation's recorded `difference`. `PUT /expenses/{id}` and `DELETE /expenses/{id}` on such a row are refused with **409** and `code = reconciliation_owned_entry`, and nothing is written on a refusal.

The refusal exists because the two link directions are asymmetric. The entry-side links are `ON DELETE CASCADE`, so deleting the **reconciliation** drops its adjustment cleanly — that is the supported way to change or remove one (re-running a reconciliation recomputes it). The reverse pointers (`card_reconciliations.adjustment_expense_id`, `account_reconciliations.adjustment_expense_id` / `adjustment_income_id`) are `ON DELETE SET NULL`, so deleting the **entry** would leave the reconciliation alive with a null pointer and a `difference` it no longer applies, while the derived balance silently snapped back to its pre-true-up value.

Restored entries are exempt: restore nulls both reconciliation links (the reconciliation tables themselves are not restored), so a restored adjustment is an ordinary historical entry and stays editable and deletable.

**Payment obligation link:** `POST /expenses` accepts an optional `payment_obligation_id` (nullable). When set, the server (a) inserts the expense with the FK and (b) auto-advances the linked obligation in the same transaction — recurring obligations move `next_due_date` forward by one cycle (anchor-day preserved via `add_months_anchored`); one-off obligations flip `is_active=false`. The FK is also editable on `PUT /expenses/{id}` via JSON Merge Patch semantics (omit = unchanged, explicit `null` = clear). The FK is returned by `GET /expenses/{id}` and the list response. **Symmetric edit model (Phase 3, follow-up Items 10 + audit round 2):** PUT detects per-FK transitions and fires the corresponding plan helpers atomically — `X → null` (clear) reverses the OLD obligation IF this expense was its most-recent linked; `null → Y` (add) advances the NEW obligation; `X → Y` (swap, same type or cross-type) fires reverse on X AND advance on Y. **Reverse advance on delete:** if the deleted expense is the most-recent linked for its obligation, the server walks `next_due_date` back one recurrence cycle (recurring) or re-activates the row (one-off) atomically with the delete. Middle-of-chain deletions leave the cursor alone.

**Subscription / installment link:** `POST /expenses` also accepts optional `subscription_id` and `installment_id` (both nullable, mutually exclusive with `payment_obligation_id`). At most one of the three FKs may be set on the same row — an expense pays exactly one commitment-type. The same JSON Merge Patch convention applies on `PUT /expenses/{id}`: omit a key to leave the link untouched, send `null` to clear it. **Advance rule (Phase 3, follow-up Item 9, Option C):** when a manual entry's closest cycle equals the current cursor (`closest == next_billing_date` for subscriptions / `idx == current_installment` for installments), the server advances the cursor one step. When the closest cycle is _ahead_ of the cursor (pre-pay / mis-click — `multi_jump`), the link is saved but the cursor stays put; the scheduler's existing back-fill loop + the partial UNIQUE INDEX dedup handle catch-up naturally so intermediate cycles still get expense rows. Back-dated entries also never advance. **Reverse advance (Phase 3, follow-up Item 10):** symmetric to obligations — deleting or unlinking the most-recent linked expense walks the cursor back one cycle / cuota and re-activates fully-paid installments when the reverse moves the cursor back inside the cuota grid. **Date edit (audit round 2):** editing a linked expense's date without changing the FK recomputes the cursor on the same subscription / installment — the old date's advance is reversed and the new date's advance re-applied — so moving a Mark-Paid entry off its cycle no longer orphans it. (Obligations are exempt: they archive with no cursor.) The matching window is implicit in the closest-cycle math: an entry advances when it is closer to the current cursor than to either neighbouring cycle — effectively a half-cycle band on each side (~15 days for monthly, ~3 for weekly, ~45 for quarterly, ~6 months for annual).

**Pre-pay multiple cycles (Phase 3, follow-up Item 2):** `POST /expenses` accepts an optional `cycles_to_advance: int` (default `1`, min `1`, max `12`). When `> 1` the server inserts that many expense rows atomically — all sharing the same `date`, `amount`, `currency`, `category`, `payment_method`, `credit_card_id`, and `payment_obligation_id` — and walks `next_due_date` forward by the corresponding number of recurrence cycles in the same transaction. `cycles_to_advance > 1` requires `payment_obligation_id` to be set (returns 422 from the schema validator otherwise) and the obligation must be recurring (returns 400 from the service otherwise). The response carries the **last** inserted expense, with `advance_change.previous_cursor` set to the obligation's cursor _before_ the loop and `advance_change.new_cursor` set to its final position _after_ the N-th advance. Use case: pre-paying several cycles of a recurring obligation in one Mark Paid click without N separate clicks.

**Mutation response — symmetric cursor changes (Phase 3, follow-up Item 7 + audit round 2):** `POST /expenses` and `PUT /expenses/{id}` return the saved expense with two optional fields, `advance_change` and `reverse_change`. `POST` populates `advance_change` when a linked FK triggered an advance (Mark Paid / create with FK). `PUT` can populate either field independently OR both simultaneously: a FK swap fires reverse on the OLD plan AND advance on the NEW plan in the same transaction, and a same-plan date edit likewise fires reverse (old date) then advance (new date) on the one plan. `DELETE /expenses/{id}` returns `{ "reverse_change": ... }` (was `204 No Content` before Item 10; delete never advances). Each cursor-change shape: `{ plan_type, plan_id, plan_name, previous_cursor, new_cursor, total_count }`. `plan_type` is one of `"obligation" | "subscription" | "installment"`; `previous_cursor` and `new_cursor` are stringified — ISO date for obligation/subscription, decimal index for installment; `new_cursor` is empty when the plan archived (one-off obligation Marked Paid, installment past its final cuota), `previous_cursor` is empty when the plan re-activated via reverse. `total_count` is the installment plan's `installments_count` (used by the client to render "cuota N of M" without an extra lookup) and is `null` for obligations and subscriptions.

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

**Card fields:** `name`, `closing_day` (1-31), `due_day` (1-31), `currency` (ISO 4217 — the card's primary/statement currency), `is_active` (boolean), `monthly_payment` (optional Decimal ≥ 0 — typical monthly payment for revolving-debt users; counts as a fixed commitment on the dashboard Liquidity card when set; null = pay-in-full, excluded from the ratio), `default_account_id` (optional — the cash/bank account this card is normally paid from, i.e. _débito automático_; it may be denominated in **any** currency and need only be owned by you (404 `not_found`); send `null` to clear), `has_expenses` (computed, read-only), `balances` (computed — list of `{currency, balance}` per currency with activity; primary always present, others added by expense activity in non-primary currencies; balances are NOT converted across currencies).

**What `default_account_id` does — and deliberately does not do.** It only **pre-fills** the account on a settlement you record, never the amount. Renly never generates a settlement from it: a real auto-debit can fail, and inventing a payment that did not happen would leave you deleting a phantom one.

**Its currency is unrestricted, unlike a recurring plan's.** Paying a USD card from your peso account is a normal arrangement, and a settlement can record it exactly (see [Cross-currency settlement](#credit-cards)), so nothing about the pair needs to match — changing a card's currency never invalidates its default, and an account referenced only as a **card's** default can still be re-denominated. A **plan's** default must still match, because a plan's charge carries a single amount with no second figure to record; an account referenced as a plan default is therefore currency-locked (409 `account_currency_change_blocked_by_default`).

**Archive behavior:** Archived cards are hidden from the expense form's card selector but retain all linked expenses and settlements. Bucket balances are still computed normally. Delete is only allowed when the card has no linked expenses (409 otherwise).

**Settlement fields:** `date`, `amount`, `currency` (required — selects which bucket the settlement reduces), `account_id` (optional — the cash/bank account the payment was drawn from, which is what makes paying a card net-worth-neutral; it may be denominated in **any** currency), `account_amount` (optional — what left that account, in **its own** currency), `account_name` / `account_currency` (computed, read-only — that account's name and currency, denormalized so an **archived** account still reads by name), `notes` (optional). Settlements have no statement-period link; per-statement amounts are derived as running-balance snapshots at the period's closing date.

**Cross-currency settlement — paying a USD bucket with pesos.** `amount`/`currency` are the **card leg**: what the payment cleared off the bucket. `account_amount` is the **cash leg**: what the bank actually debited from the funding account, in that account's currency. Both are recorded and the pair _is_ the record of the rate used — no rate is stored, because no single direction reads correctly for both paying a bill and receiving a refund. The gap between the two is the real FX + tax cost and is never itemised: the Argentine "dólar tarjeta" already contains the ~30% Ganancias perception, so there is no separable figure to record and adding one would double-count. Because outstanding card debt is valued at your chosen dollar rate, clearing it lowers your net worth when that rate sits below the card rate and can read as a small gain when it sits above — the same mark-to-market effect any foreign-currency debt has. Reconciliation stays the generic tax/fee catch-all.

Rules (all 400, all carrying a machine `code`):

- Currencies differ and `account_amount` is missing → `settlement_account_amount_required`. Only you know the blended rate your bank charged, so it cannot be inferred.
- Currencies match and `account_amount` differs from `amount` → `settlement_amounts_must_match`. No conversion happened, so the account must be debited exactly what came off the bucket; record a bank fee as its own expense.
- `account_amount` without `account_id` → `settlement_account_amount_without_account`.

A same-currency settlement stores `account_amount` as `null`, so a non-null value always means the two currencies differed. Every balance that counts cash reads `account_amount` when present and `amount` otherwise; the card's own bucket balance always reads `amount`, since the bank cleared the bill in the bucket's currency.

### Card Reconciliations (Phase 3, Step 5)

Per-bucket, per-statement true-up against the bank. Captures fees / FX / taxes / timing that fall outside the app's normal model. See [Credit Card Liability Model](../technical/credit-card-liability-model.md) for the full math.

| Method   | Path                                       | Description                                                                                                                                                               |
| -------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`    | `/credit-cards/{id}/reconciliations`       | List reconciliations for a card. Optional `currency` filter selects a single bucket.                                                                                      |
| `GET`    | `/credit-cards/{id}/statements`            | List recent statement periods per bucket with `Reconciled` / `Not reconciled` / `Stale` status. Drives the Reconciliations sub-section UI.                                |
| `POST`   | `/credit-cards/{id}/reconciliations`       | Create-or-replace a reconciliation. If one exists for the same `(currency, period_start, period_end)`, it (and its adjustment) is deleted before the new pair is written. |
| `DELETE` | `/credit-cards/{id}/reconciliations/{rid}` | Delete a reconciliation. Cascade-deletes its adjustment expense.                                                                                                          |

**`POST` body:** `currency`, `period_start`, `period_end`, `statement_balance`. The server computes `computed_balance` (= running balance at `period_end` for the bucket), `difference = statement_balance − computed_balance`, and creates one **signed, card-linked `expense_entries` row** (`source='reconciliation'`): a positive amount with category `card_fees_and_taxes` when `difference > 0`, a negative amount with category `card_credits_and_refunds` when `difference < 0`, and none when `difference == 0`. An expense is the only row type that can move a bucket (the balance is `Σ expenses − Σ settlements`), so a credit recorded any other way would leave the card overstated. The adjustment is dated on `period_end` so it flows naturally into the next period's running balance. A credit is never account-linked — it clears card debt without moving cash; a refund paid back to your bank is ordinary account-linked income instead. The adjustment row is **read-only** through the expense endpoints (409 `reconciliation_owned_entry`); change it by re-running or deleting this reconciliation.

**Reconciliation fields:** `id`, `card_id`, `currency`, `period_start`, `period_end`, `statement_balance`, `computed_balance`, `difference`, `adjustment_expense_id`, `adjustment_income_id`, `is_stale` (flipped to `true` when anything the recorded figures were derived from has since changed — see below), `reconciled_at`.

**When a card reconciliation goes stale.** A statement's `computed_balance` is the bucket's running balance at `period_end`, which sums **all** charges and settlements up to that date, not just those inside the period. So a reconciliation is flagged stale whenever a charge or settlement dated **on or before its `period_end`** is created, edited or deleted after it was recorded — including one dated before the period began — and also when an **older** period is reconciled or un-reconciled, because the adjustment that posts (or disappears) is itself a dated row inside every later balance. Re-running the affected statement recomputes it and clears the flag.

Unlike account reconciliation, reconciling card statements **out of order is allowed**. Re-running a card statement replaces it — the prior row and its adjustment are dropped and the figures are recomputed from scratch — so re-running the flagged statements oldest-first always converges. A period whose closing date is still in the future is rejected with **400** `card_reconciliation_future_period`: there is no statement to reconcile against yet.

**Statement-period semantics:** A statement is identified by its closing date. The period spans `(prev_closing_date, this_closing_date]` — the closing date is the LAST day of the statement it closes; the next statement starts the day after. Day-of-month overflow (e.g. `closing_day = 31` in February) is resolved by clamping to the last day of the target month.

**Uniqueness:** `(card_id, currency, period_start, period_end)`. `POST` always behaves as create-or-replace.

---

## Accounts

Cash / bank / wallet accounts — the asset side of net worth (the mirror of credit-card liabilities). Each account has one currency. The balance is derived at query time: `opening_balance + linked income − linked expenses − settlements paid from the account + transfers in − transfers out`. Expenses, income, and settlements each carry an optional `account_id` linking them to an account (a NULL link is unattributed and affects no balance), and both legs of an account-to-account transfer count on their own side. Expenses and income must match the account's currency; a **card settlement may cross it**, and then contributes the `account_amount` it recorded rather than what it cleared off the card. An account's currency is fixed once entries link to it (a change is rejected with 409), so the balance never mixes currencies.

| Method   | Path                       | Description                                                     |
| -------- | -------------------------- | --------------------------------------------------------------- |
| `GET`    | `/accounts`                | List accounts with search, sorting, and balances.               |
| `POST`   | `/accounts`                | Create a new account.                                           |
| `GET`    | `/accounts/{id}`           | Get a single account with its current balance.                  |
| `PUT`    | `/accounts/{id}`           | Update an account. Only provided fields are changed.            |
| `DELETE` | `/accounts/{id}`           | Delete an account (linked entries are un-attributed, not lost). |
| `POST`   | `/accounts/{id}/archive`   | Archive an account (hide from active selection).                |
| `POST`   | `/accounts/{id}/unarchive` | Restore an archived account.                                    |
| `GET`    | `/accounts/{id}/movements` | The account's ledger: every movement that reached it.           |

**List query parameters:** `search` (filter by name), `sort_by` (`name`, `type`, `currency`, `opening_date`), `sort_order` (`asc`/`desc`), `show_archived` (boolean, default `false` — include archived accounts).

### Account ledger

`GET /accounts/{id}/movements` returns every movement that reached one account — income, expenses, card settlements, both transfer legs, and the adjustments an account reconciliation posts — as one paginated list, newest first.

**Query parameters:** `kind` (filter: `income`, `expense`, `transfer`, `settlement`, `adjustment`), `page` (1-based; a page past the end is clamped to the last page that has rows), `page_size` (default 25, max 100).

**Response:** `items`, `total`, `page`, `page_size`, and `currency` — carried once for the whole page rather than per row, because it cannot vary: an income or expense entry is validated to match the account's currency, each transfer leg is stored in its own account's, and a card settlement records what left the account separately from what it cleared.

**Movement fields:** `source` (the table it was read from: `income`, `expense`, `settlement`, `transfer` — with `source_id` it identifies the row, which `kind` alone cannot, since `adjustment` spans two tables), `source_id`, `kind` (what it is from the account's point of view; a reconciliation's adjustment reads as `adjustment` rather than as the income or expense row it is stored as, and a transfer is one kind in both directions), `date`, `amount` (**signed** in the account's currency: positive in, negative out), `balance_after` (the account's balance immediately after this movement — **null while a `kind` filter is active**, because consecutive visible rows would otherwise differ by amounts the filter hides), `category`, `counterparty` (the card a settlement paid, or the other account of a transfer), `counterparty_amount` / `counterparty_currency` (the other side — a transfer's far leg, or the card amount a settlement cleared — which differ from `amount` only across currencies, so a cross-currency card payment renders the pair exactly like a cross-currency transfer), and `notes`.

Movements dated before the account's `opening_date` are excluded, because `opening_balance` is by definition the balance at that date and already contains them — the same bound every balance sum applies.

**Account fields:** `name`, `type` (`cash`, `bank`, `wallet`, `other`), `currency` (ISO 4217 — one of the exchange-rate-supported set; rejected with 422 otherwise), `opening_balance` (Decimal; may be negative), `opening_date` (the date the opening balance is measured at — anchors the historical series; like `currency`, it is locked once entries link to the account, since every balance sum is bounded by it and `opening_balance` cannot be recomputed — 409 `account_opening_date_change_blocked`), `is_active` (boolean), `notes` (optional), `balance` (computed, read-only — the account's current balance in its own currency: `opening_balance + linked income − linked expenses − settlements paid from it + transfers in − transfers out`, every term bounded below by `opening_date` because `opening_balance` already is the balance at that date), `has_links` (computed, read-only — whether any entry links the account; when true, its currency is locked), `last_reconciled_date` (computed, read-only — the date of the most recent reconciliation, or null).

### Transfers

Money moving between two accounts you own. Neither income nor an expense — net worth does not change.

| Method   | Path              | Description                                     |
| -------- | ----------------- | ----------------------------------------------- |
| `GET`    | `/transfers`      | List your transfers, newest first.              |
| `POST`   | `/transfers`      | Record a transfer between two of your accounts. |
| `GET`    | `/transfers/{id}` | Get a single transfer.                          |
| `PUT`    | `/transfers/{id}` | Update a transfer. Only provided fields change. |
| `DELETE` | `/transfers/{id}` | Delete a transfer; both balances recompute.     |

**List query parameter:** `account_id` — only transfers touching that account, on **either** leg.

**Request fields:** `from_account_id`, `to_account_id`, `date`, `from_amount` (> 0), optional `to_amount` (> 0) and `notes`.

**The two amounts.** `from_amount` is in the source account's currency, `to_amount` in the destination's.

- **Same currency:** omit `to_amount` and it mirrors `from_amount`. Sending a _different_ value is rejected (400 `transfer_amounts_must_match`) rather than silently overwritten — a transfer that credits less than it debits would destroy net worth, so record a bank fee as its own expense.
- **Different currencies:** `to_amount` is **required** (400 `transfer_amount_required` otherwise). The pair is the record of the rate actually used, spread included; no stored rate can reconstruct it.

Both accounts must be yours (404 otherwise), must differ (400 `transfer_same_account`), and the date must be on or after **both** accounts' opening dates (400 `transfer_before_account_opened`) — otherwise the transfer would be counted against one account and not the other, moving your net worth. On `PUT`, the currency rules are re-checked against the **effective** pair, so moving one leg to an account in another currency is validated as the new shape.

**Response fields:** the request fields plus `from_account_name` / `to_account_name` and `from_currency` / `to_currency`, denormalized so a client renders a row without a second lookup. There is deliberately **no** implied-rate field: any single derived number has to pick a direction that only reads correctly one way (buying dollars wants "1200 ARS per USD", selling wants the reciprocal), so clients render the pair instead.

Deleting an account deletes the transfers referencing it — a surviving half-transfer would skew the other account's balance.

### Account reconciliation

Linking every movement to an account is optional, so a derived balance drifts from the real one. Reconciliation is how you snap it back: enter the balance the account **actually** shows on a date, and Renly records that figure and posts a **single adjustment entry** on that date for the difference — no back-filling history required.

The adjustment is an income when the account really holds more than Renly computed, an expense when it holds less, and nothing at all when the two already agree. It is dated on `as_of_date`, linked to the account (so it enters the running balance from there forward), and categorised `account_adjustment` so true-ups are easy to tell apart from itemised spending. This is also the general catch-all for bank fees, interest, FX spread, and taxes — anything that moved the real balance without a matching entry lands in the difference, with no per-fee bookkeeping.

The category labels a true-up; it does not hide it. Adjustments still count toward your income and expense totals and appear in the category breakdown — the money really did move, it just was never itemised. The card reconciliation categories behave the same way.

Reconciling is repeatable, and works forward: a later reconciliation simply appends and the most recent one wins. Re-running the same date is self-correcting — the earlier adjustment is already part of the computed balance, so the difference comes out zero and nothing new is posted. Reconciling a date **earlier** than the account's latest reconciliation is rejected (400 `account_reconciliation_before_last`): its adjustment would post underneath the newer reconciliation, which is bounded to its own date and cannot see it, leaving that newer balance wrong. To revise an older date, delete the newer reconciliation first.

| Method   | Path                                   | Description                                                              |
| -------- | -------------------------------------- | ------------------------------------------------------------------------ |
| `GET`    | `/accounts/{id}/computed-balance`      | The account's derived balance at a date (drives the difference preview). |
| `GET`    | `/accounts/{id}/reconciliations`       | List an account's reconciliations, newest first.                         |
| `POST`   | `/accounts/{id}/reconciliations`       | Reconcile the account against its real balance.                          |
| `DELETE` | `/accounts/{id}/reconciliations/{rid}` | Delete a reconciliation (also removes the adjustment it created).        |

**Computed-balance query parameters:** `as_of_date` (required) — the date to compute at.

**Reconciliation request fields:** `as_of_date` (the date the real balance was read — today or earlier, not before the account's `opening_date`, and not before the account's most recent reconciliation; all three rejected with 400) and `statement_balance` (Decimal; may be negative for an overdraft).

**Reconciliation fields:** `as_of_date`, `statement_balance`, `computed_balance` (what Renly derived at that date, recorded at the time), `difference` (`statement_balance - computed_balance`), `adjustment_expense_id` / `adjustment_income_id` (whichever entry was created, if any), `reconciled_at`.

Deleting a reconciliation cascades to its adjustment entry, so the balance returns to what it was before the true-up — the escape hatch for a mistyped figure. Only the account's **most recent** reconciliation can be deleted (400 `account_reconciliation_not_latest` otherwise), because an older one's adjustment is already baked into every later reconciliation's recorded `computed_balance`. Delete newest-first.

Deleting the reconciliation is the **only** way to remove its adjustment: the adjustment entry itself is read-only through the expense and income endpoints (409 `reconciliation_owned_entry`), because removing it directly would orphan this reconciliation rather than cascade through it.

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

**Subscription fields:** `name`, `amount` (> 0), `currency` (ISO 4217), `billing_cycle` (`monthly`, `annual`, `quarterly`, `biweekly`, `weekly`), `payment_method` (optional; `cash`, `debit`, `transfer`, `credit_card`), `credit_card_id` (when payment_method = credit_card), `default_account_id` (optional — the cash/bank account this plan is paid from; see below), `is_active`, `next_billing_date`. Responses also include `converted_amount` when `currency` query param is provided.

**Default funding account (`default_account_id`).** Optional on all three plan types: the cash/bank account the plan is paid from. It must be denominated in the plan's own currency (400 `account_currency_mismatch`) and owned by you (404 `not_found`), and it is rejected when `payment_method` is `credit_card` (400 `account_card_exclusivity`) — a card-paid plan increases the card's balance and only draws cash later, at the card settlement, so its cash leg belongs to the card's own default instead. For **subscriptions and installments** the nightly scheduler links every charge it emits to that account, so an auto-generated expense decrements the balance it really came out of; for **payment obligations**, which are never auto-emitted, it pre-fills "Paid from" on the expense Mark Paid creates. Already-emitted expenses are never rewritten. Send `null` to clear. If the account later stops qualifying — archived, or its own currency changed while nothing but this default referenced it — the scheduler emits the charge **unlinked** rather than skipping it. A charge dated before the account's `opening_date` is likewise emitted unlinked, since every balance sum is bounded below by that date and the link would not move the balance.

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

**Installment fields:** `name`, `total_amount` (> 0), `installment_amount` (> 0), `currency`, `installments_count` (≥ 1), `current_installment` (≥ 1; default 1), `payment_method` (optional), `credit_card_id` (optional), `default_account_id` (optional — the cash/bank account this plan is paid from; see below), `is_active`, `start_date`. Responses also include `next_cuota_date` (computed = `start_date + (current_installment - 1) months` with month-end clamping; `null` once the plan is fully paid) and `converted_total_amount` / `converted_installment_amount` when `currency` query param is provided.

**Default funding account (`default_account_id`).** Same rule and behaviour as on subscriptions — see [Subscriptions](#subscriptions).

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

**Obligation fields:** `name`, `amount` (> 0), `currency`, `next_due_date` (anchor for the next occurrence — recurring obligations project forward from this), `recurrence` (optional; `monthly`, `bimonthly`, `quarterly`, `annual`, or omitted for one-off), `category` (optional, free-form user label, max 100 chars — e.g. "ABL", "Cable"), `expense_category` (optional, structured enum reusing `ExpenseCategory` — used to pre-fill Mark Paid + feed finance breakdowns), `payment_method` (optional), `credit_card_id` (optional), `default_account_id` (optional — the cash/bank account this plan is paid from; see below), `is_active`, `notes` (optional), `last_payment_date` (computed, read-only — date of the most recent linked expense, surfaces on archived one-off rows as a "Paid on" indicator). Responses include `converted_amount` when `currency` query param is provided.

**Default funding account (`default_account_id`).** Same rule and behaviour as on subscriptions — see [Subscriptions](#subscriptions).

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

**Subscription / installment projection (Phase 3 follow-up):** Symmetric to obligations. Forward walker emits unpaid future cycles (subscription billing cycles from `next_billing_date`; installment cuotas from `current_installment` to `installments_count`). Backward walker emits past PAID cycles: each linked expense is bound to the cycle (or installment cuota) its date is closest to — the same closest-cycle rule the manual-entry advance uses — so a payment logged a few days off the cycle date still marks that cycle Paid, not just an exact-date match. Past-paid items use the linked expense's historical amount + currency.

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
| `GET`  | `/dashboard/overview`    | Net worth, its Yours/Shared split, investment KPIs, finance KPIs, savings rate, income/expense ratio.      |
| `GET`  | `/dashboard/evolution`   | Monthly net worth series (investments + cash − card debt + your share of everything shared, per month).    |
| `GET`  | `/dashboard/composition` | Allocation by category plus cash, what your groups owe you, and a liabilities segment.                     |
| `GET`  | `/dashboard/liquidity`   | Liquidity health indicator: fixed monthly commitments / monthly income ratio classified against threshold. |

**Query parameters (overview + evolution):** `currency`, `date_from` (YYYY-MM-DD), `date_to` (YYYY-MM-DD).

**Query parameters (composition + liquidity):** `currency` only (no date filtering — shows current snapshot).

**Overview response:** `net_worth`, `private_net_worth`, `shared_net_worth`, `shared_pot_value`, `shared_receivable`, `shared_payable`, `has_shared`, `undivided_pots[]`, `net_worth_change`, `net_worth_change_pct`, `investment_total`, `investment_gain`, `investment_gain_pct`, `investment_month_change`, `investment_month_change_pct`, `cash_total`, `credit_card_balance`, `total_income`, `total_expenses`, `savings_rate` (null when no income), `income_expense_ratio` (null when no expenses), `has_holdings`, `skipped_currencies`. `net_worth_change` covers investments, cash, card debt and the shared side together; `investment_month_change` stays investment-only. `has_holdings` reports whether the user holds anything at all — investment, account, card, or a shared side — i.e. whether the net-worth figure is derived from anything; it stays `true` when the figures happen to net to zero, so it is not a `net_worth != 0` test.

**What "shared" counts, and what it never counts.** `net_worth` is everything you are worth: your private holdings plus your share of everything you share. `private_net_worth` and `shared_net_worth` split it and always sum to it exactly. The shared half is your share of every pot you can see, plus what your groups owe you, less what you owe them — a receivable is an asset and a payable a liability, each on its own line and never blended into cash.

**Visibility never inflates it.** A pot you may see but own none of contributes exactly zero, and so does one whose owners have not agreed a division yet — before that baseline nobody owns any share of anything. Those pots are listed in `undivided_pots[]` (`pot_id`, `name` — null for a group's default pot — `group_id`, `group_name`) so the surface can say why value it can see is not in the total. A pot you may NOT see contributes nothing and is not named: a figure derived from it would disclose what the policy hides.

**`cash_total` and `investment_total` count the same universe the composition does** — your own holdings plus your share of pot-held ones. `investment_gain` does not: a pot share has no invested figure of its own, and your exposure to it changes whenever units are issued, so the return stays your private holdings' and the surface says so.

**Evolution response:** `points[]` with `date`, `investment_value`, `cash_balance`, `card_balance`, `shared_value`, `private_net_worth`, `net_worth` per month, plus `skipped_currencies`. The grid runs from the earliest month ANY term begins — your first snapshot, an account's opening date, a card's first charge, or a pot's ownership baseline — through the current calendar month, clipped to the requested window at both ends. Investments and card debt forward-fill onto it; cash and the shared side are derived at each month end rather than accumulated, so each is converted at that month's rate.

**Composition response:** `items[]` with `label` (category name, `"cash"`, `"receivable"`, or `"liabilities"`), `value`, `percentage`. Plus `total_assets`, `total_liabilities`, `skipped_currencies`. Your share of a co-owned holding lands in the slice its own kind belongs to — a jointly held CEDEAR in `cedears`, a jointly held bank account in `cash` — because the donut answers "what is my money in" and scope is not an asset class. What your groups owe you is its own asset slice; what you owe them joins liabilities. A net-negative cash total is left out of the asset breakdown (the same treatment as a card in net credit).

**Liquidity response:** `ratio` (null when income is zero or history too short), `state` (`healthy` / `caution` / `at_risk` / `unknown`), `fixed_monthly_commitments`, `monthly_income`, `threshold` (integer percent), `income_window_days` (target = 90), `actual_window_days` (smaller during early app life), `currency`, `skipped_entities` (defensive diagnostic listing any commitment whose currency couldn't be converted — always empty in practice today). Commitments amortise subscriptions / installments / recurring obligations to a monthly base, plus any credit card with `monthly_payment` set (revolving-debt users); income is the user's last 90 days (or actual elapsed days, minimum 7) normalised to 30. Configure the threshold via `liquidity_threshold_pct` on settings.

**Classification bands:** `healthy` when `ratio × 100 < threshold`; `caution` when `threshold ≤ ratio × 100 < threshold + 10`; `at_risk` when `ratio × 100 ≥ threshold + 10`; `unknown` when income is zero or the user has fewer than 7 days of income history. The +10pp caution band is hardcoded.

**Net worth formula:** `investment_total + cash_total - credit_card_balance`. Cash comes from your accounts (see [Accounts](#accounts)); each account balance is converted to the display currency at today's rate for current figures and at each month-end for the historical series.

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
| `max_collections`              | int      | Maximum number of collections the user can create.                                                                                                                                                                                  |
| `collection_warning_pct`       | number   | Percentage threshold that triggers a collection-limit warning.                                                                                                                                                                      |
| `dollar_rate_preference`       | string   | Which USD/ARS rate to use for conversions: `oficial`, `mep`, or `blue`.                                                                                                                                                             |
| `shortcut_currencies`          | string[] | Currencies shown in the iOS Shortcut currency picker.                                                                                                                                                                               |
| `timezone`                     | string   | User's IANA timezone (e.g. `America/Argentina/Buenos_Aires`). Used by the auto-expense scheduler to fire cycles on the user's local calendar day. Defaults to UTC when unset. Validated server-side; invalid IANA names return 400. |
| `timezone_mode`                | string   | `auto` or `manual`. In `auto`, the browser-detected timezone is silently kept in sync on every protected page load. In `manual`, the stored value never changes automatically.                                                      |
| `language`                     | string   | User's preferred language code (`en` or `es`). Drives next-intl message loading and the language of transactional emails.                                                                                                           |
| `language_mode`                | string   | `auto` or `manual` — same semantics as `timezone_mode` but for language.                                                                                                                                                            |
| `liquidity_threshold_pct`      | int      | Liquidity-alert threshold as integer percent (1–99). Drives the `/dashboard/liquidity` state classification. Null falls back to the backend default (`40`).                                                                         |
| `savings_rate_healthy_pct`     | int      | Savings rate at or above this percent renders the Savings Rate dashboard card green. Default 20 when null.                                                                                                                          |
| `savings_rate_moderate_pct`    | int      | Savings rate below healthy but at or above this renders amber. Below this renders red. Default 10 when null.                                                                                                                        |
| `income_expense_ratio_healthy` | Decimal  | Income/expense ratio at or above this renders the Income/Expense dashboard card green. Break-even (1.0) is the amber pivot. Default 1.5 when null. Range `[0.1, 10.0]`. Stored as string in JSONB to preserve precision.            |
| `onboarding_completed`         | bool     | Whether the user has finished or dismissed first-run onboarding. `null` for a fresh user; set `true` to stop the dashboard welcome from showing.                                                                                    |

---

## Onboarding

First-run onboarding state for the authenticated user, all derived from the account's real data (no per-step flags to keep in sync): the dashboard welcome's reactive checklist, the per-section first-run sample data, and the welcome tour's seen-state. Each `sample_*` flag is true only while that section is empty **and** the user hasn't yet created that entity or cleared its sample — so each section teaches once, independently. `tour_completed` is a dedicated flag (separate from `onboarding_completed`) so the guided tour and the checklist don't suppress each other. The `onboarding_completed` field under [Settings](#settings) remains the welcome's "hide forever" flag.

| Method | Path                                   | Description                                                                                                       |
| ------ | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/onboarding/status`                   | Checklist completion + per-section sample flags + tour state for the current user.                                |
| `POST` | `/onboarding/samples/{entity}/dismiss` | Retire (hide) one section's first-run sample. `{entity}` = `investments`, `expenses`, or `income`. Returns `204`. |
| `POST` | `/onboarding/tour/complete`            | Mark the first-run welcome tour finished/dismissed so it never auto-shows again. Returns `204`.                   |

**Response fields (`GET /onboarding/status`):**

| Field                  | Type | Description                                                       |
| ---------------------- | ---- | ----------------------------------------------------------------- |
| `has_investments`      | bool | The user has created at least one investment.                     |
| `has_finances`         | bool | The user has recorded at least one income or expense entry.       |
| `has_accounts`         | bool | The user has created at least one cash or bank account.           |
| `primary_currency_set` | bool | The user has explicitly chosen a primary display currency.        |
| `sample_investments`   | bool | Whether the investments section should show its first-run sample. |
| `sample_expenses`      | bool | Whether the expenses section should show its first-run sample.    |
| `sample_income`        | bool | Whether the income section should show its first-run sample.      |
| `tour_completed`       | bool | Whether the user has finished or dismissed the welcome tour.      |

---

## Administration (invite-only access)

Admin-only, and **admin here means account administration, not visibility**: `is_admin` gates who may hand out access to Renly itself. It grants no additional sight of anyone's data — the same rule the group `admin` role follows. A non-admin gets `403 admin_required` from every endpoint below; the web additionally answers a real `404` on the admin page, so its existence is not advertised.

These matter only while `SIGNUP_MODE=invite`. In `open` mode anyone can sign up, so there is nobody to invite, and the page is gone for everyone — admins included — rather than showing an empty list.

| Method | Path                         | Description                                                                                                                   |
| ------ | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/admin/invites`             | Every invite with its effective status. Spans all invites, not only the ones you created.                                     |
| `POST` | `/admin/invites`             | Invite an email and send it a signup link. Body: `email`. `409 invite_email_taken` if that address already has an account.    |
| `POST` | `/admin/invites/{id}/resend` | Re-arm the invite with a fresh token and send the link again. `404` if unknown, `409` once it has been accepted.              |
| `POST` | `/admin/invites/{id}/revoke` | Kill a pending invite's link. `404` if unknown, `409` once accepted — the account exists, so there is nothing left to revoke. |

Each invite reads back as `{ id, email, status, invited_by, expires_at, consumed_at, created_at }`. **`status` is effective, not stored:** a pending invite whose `expires_at` has passed reports `expired`, so the list never shows a link as usable once it is not. The four values are `pending`, `accepted`, `revoked` and `expired`.

Creating and resending are rate-limited, and **the raw token is never returned** — it exists only inside the emailed link. That is why a lost invite is replaced by resending it (a fresh token, the previous one dead) rather than looked up.

---

## Groups (shared money)

A **group** is a set of people who share money — a household, a couple, a trip, a flat share. It is the only entity in Renly that more than one account can reach: everything else belongs to exactly one person. A group holds _who the people are_ and nothing about what they share.

Two rules govern every endpoint here:

- **Ownership is a property of the record, never of the login.** A group's rows belong to the group, and are visible to its active members.
- **Administration never grants visibility.** The `admin` role gates changes to members, settings and invites. It grants **no** additional access to anyone's data — an admin sees exactly what a member sees.

Each **member** is a seat in the group. A seat may be linked to a Renly account, or be a **name-only placeholder** for someone who has no account (and may never have one) — they still get a real place in the group. Removing a member deactivates their seat rather than deleting it, so the group's history stays readable and an admin can bring them back.

| Method   | Path                                      | Description                                                                                                              |
| -------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `GET`    | `/groups`                                 | List the groups you belong to, each with its full roster, your role, and its active member count.                        |
| `POST`   | `/groups`                                 | Create a group. Body: `name`, `kind`, optional `display_name`. You become its first admin.                               |
| `GET`    | `/groups/{id}`                            | Get one group with its roster. `404` if it doesn't exist **or** you aren't a member — the same answer either way.        |
| `PUT`    | `/groups/{id}`                            | Update `name` and/or `kind`. Admin only.                                                                                 |
| `DELETE` | `/groups/{id}`                            | Delete the group with every seat and invite in it. Admin only.                                                           |
| `POST`   | `/groups/{id}/members`                    | Add a name-only seat. Body: `display_name`, optional `role`. Admin only.                                                 |
| `PUT`    | `/groups/{id}/members/{member_id}`        | Update `display_name` or `role`, or pass `is_active: true` to bring a former member back. Admin only.                    |
| `DELETE` | `/groups/{id}/members/{member_id}`        | Remove a member: deactivates the seat and drops its pending invite. Admin only — **except** removing your own (leaving). |
| `POST`   | `/groups/{id}/members/{member_id}/invite` | Create or rotate that seat's invite. Body: optional `email`. Admin only. Returns the link.                               |
| `DELETE` | `/groups/{id}/members/{member_id}/invite` | Revoke the seat's invite so its link stops working. Admin only.                                                          |

`kind` is one of `household`, `couple`, `trip`, `flat`, `other`. `role` is `admin` or `member`.

A member response reports `is_linked` (a Renly account holds this seat), `is_self`, `is_active` and `has_pending_invite` as booleans, and deliberately carries **no account id** — a client has no use for another member's, and exposing it would leak account identity across a group.

`is_active` on the `PUT` only accepts `true` — it exists to bring a former member back. Removing someone is the `DELETE` on the same path, which is also the verb that drops their pending invite and the one a member may use on their own seat; sending `false` here is a `422`.

**A group always keeps at least one active admin.** Demoting, deactivating or leaving as the last one is refused with `409 group_last_admin` — no other role can promote a replacement, so the group would be permanently unadministrable.

### Group invites

A group invite links an **existing** Renly account to one seat. It creates no account and grants **no** signup access — a separate mechanism from the `SIGNUP_MODE=invite` platform gate, which is why it lives in its own table.

Only the SHA-256 hash of the raw token is stored, so the link is returned **once**, in the reply to the request that minted it. A lost link is not recoverable — you rotate it, which also kills the previous one. Omitting `email` produces a **link-only** invite: nothing is sent and you share the URL yourself.

The token is the credential: whoever holds the link claims the seat, and their account email need not match the invited address (there is nothing being created for an address to be bound to, and a shareable link has no address to match by definition). Invites are single-use, expire after 7 days, and are revocable. Single-use holds under concurrency too — the claim takes a row lock, so if two people open the same link at once exactly one joins and the other gets `400 invalid_token`.

| Method | Path                            | Auth         | Description                                                                                         |
| ------ | ------------------------------- | ------------ | --------------------------------------------------------------------------------------------------- |
| `GET`  | `/group-invites/{token}`        | **None**     | Preview a join link: the group's name and kind, the seat's label, who sent it, and when it expires. |
| `POST` | `/group-invites/{token}/accept` | Bearer token | Claim the seat for the authenticated account. Returns the group you joined.                         |

The preview is unauthenticated because most recipients open the link with no session; it discloses nothing beyond those four fields — no roster, no other member's identity, no figures. A token that is unknown, already used, or expired returns `400 invalid_token` in all three cases, so a token cannot be probed. Claiming a seat you cannot hold — because you already have one in that group — is `409 group_membership_exists`. Inviting a seat somebody has already claimed is a different thing and answers `409 group_seat_taken`, since the caller there is an admin rather than the person already in the group.

## Pots (co-owned money)

A **pot** is the container co-ownership attaches to. Investments and cash accounts point at a pot instead of at a person, and one ownership ledger divides the whole of it — so an internal rebalance leaves everyone's share untouched. All ownership maths runs in the pot's `base_currency`, which is why it cannot be changed after creation: it is the unit of every figure already recorded.

Visibility and write access are separate questions, and both are per pot. `visibility` (`members` | `owners`) is the default for a member with no explicit permission row; a per-member row overrides it. **Write** has no such default — it is granted per member and nowhere else, so a pot can name one custodian with everyone else read-only. A member owning **0%** still sees the whole pot: membership is not ownership.

**A pot's value is `null` unless it can be stated in full.** It is the sum of what the pot holds, and a sum missing a term is not a smaller sum — so a pot holding something nobody has snapshotted on or before the date, a holding in a currency with no stored rate, or nothing at all, all answer `null` rather than a partial figure. That matters beyond display: a contribution priced against an incomplete value issues units against a figure that is not the pot's, which moves real value between owners. An **archived** holding is excluded from the value by design and so never makes it unknown.

A pot also declares a **`snapshot_cadence`** (`weekly` | `monthly` | `ad_hoc`, defaulting to monthly), and it is an _expectation_, not a schedule: nothing is snapshotted because a pot asked for one. All it decides is when the pot reads as out of date and how far apart its value series' points sit. Setting it is group administration, like the name and the visibility.

Two more fields follow from it, and they answer a **different question from `nav`** — the three can honestly disagree. `valued_as_of` is the date the value is **updated through**: the **oldest** of the pot's holdings' latest snapshots, because a total is only as current as its stalest term. Note what it is not — `nav` is still today's figure, so a pot reporting `nav: 55000` and `valued_as_of: 2026-02-28` was very probably worth something else entirely on that February date; the field says how stale the figure's oldest input is, never which date the figure belongs to. `is_stale` says that date is more than one cadence period old. So a pot whose holdings are all snapshotted but one of which cannot be converted reports a real `valued_as_of` and a `null` `nav` — the numbers are fresh, this currency just cannot state them. `valued_as_of` is itself `null` when nothing has ever been valued, which is a state of its own rather than a very old date. An **`ad_hoc`** pot is never stale, having declared no rhythm to be late against, and neither is a pot holding nothing — an overdue valuation of nothing is a demand nobody can meet. A pot holding only cash accounts is current by construction, because a balance is derived at the date it is asked for rather than recorded on one.

| Method   | Path                                 | Description                                                                                                                                      |
| -------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET`    | `/pots`                              | List every pot you may see, each with its value, unit price and ownership breakdown. Optional `?group_id=`.                                      |
| `GET`    | `/pots/{id}`                         | One pot with its breakdown. Optional `?as_of_date=` values it at a past date. `404` if hidden **or** missing — same answer.                      |
| `GET`    | `/pots/{id}/series`                  | The pot's value at each point of its cadence's grid, plus your own share value at each. Optional `?periods=` (1–52, default 12).                 |
| `POST`   | `/pots`                              | Create a pot. Body: `group_id`, `base_currency`, optional `name`, `snapshot_cadence`, `visibility`. Group admin only; you get full access to it. |
| `PUT`    | `/pots/{id}`                         | Update `name`, `snapshot_cadence` and/or `visibility`. Group admin only. `base_currency` is deliberately not updatable.                          |
| `DELETE` | `/pots/{id}`                         | Delete the pot. Group admin only; `409 pot_has_holdings` while it still holds anything.                                                          |
| `PUT`    | `/pots/{id}/permissions/{member_id}` | Grant or change a member's access. Body: `can_view`, `can_write` (which forces `can_view`). Group admin only.                                    |
| `DELETE` | `/pots/{id}/permissions/{member_id}` | Drop the explicit row, returning that member to the pot's visibility default. Group admin only.                                                  |
| `GET`    | `/pots/{id}/holdings`                | Everything the pot holds, each with its own figure and the same figure in the pot's base currency.                                               |
| `POST`   | `/pots/{id}/holdings`                | Move holdings **into** the pot. Body: `investment_ids`, `account_ids`. Needs pot write access.                                                   |
| `POST`   | `/pots/{id}/holdings/remove`         | Move them back out into your own private scope. Same body, same access.                                                                          |

Reading the holdings needs no ownership and no write access — a member holding 0% sees the whole list, because partial visibility of something you co-own is not a feature. The response splits into the same two lists the move endpoints take as input (`investments`, `accounts`), each holding carrying its `value` in its own currency and `base_value` in the pot's. Both are **null when unknown** rather than zero: an investment nobody has snapshotted yet has no value to state, and a currency with no stored rate cannot be restated in the pot's. Unlike the NAV — which refuses to report a total it cannot compute in full — one unconvertible holding costs only its own `base_value`; the rest of the list still says what it knows.

**Archived holdings are listed too**, flagged by `is_active`. An archived holding contributes nothing to the NAV, but it still points at the pot, so it still blocks deleting the pot and still has to be movable back out — a read that hid it would show an empty pot that refuses to be deleted, with nothing to explain why.

Each holding also carries **`valued_on`**, the date its figure was recorded. It is what the pot's `valued_as_of` is the oldest of, so a pot reading overdue can say _which_ holding is responsible instead of leaving the reader to guess. It is `null` for a cash **account**: a balance is derived at the moment it is asked for rather than recorded on a date, so there is none to state, and an account can therefore never be the stale one.

### The value series

`GET /pots/{id}/series` answers "how has this been going", which is the question the rest of the pot page cannot. It returns `interval` (`weekly` | `monthly`) and `points`, oldest first, the last of which is **today**. Every earlier point is a real calendar boundary — a month's last day, or a week's Sunday — so a pot snapshotted on the rhythm Renly's own auto-snapshots keep has a figure at each of them rather than reading one period behind.

`interval` is the grid, **not** the pot's cadence: an `ad_hoc` pot declares no rhythm and is plotted monthly, so echoing its cadence would describe the points wrongly.

Each point carries `nav` and `my_value`, both in the pot's base currency and **both null wherever the value cannot be stated in full on that date** — the same rule the headline NAV follows, applied per date. On a real pot most of the early points are null, because a holding moved in last month has no valuation for the months before it, and drawing a zero there would read as growth from nothing. `my_value` is additionally null while **no units are outstanding**: before the ownership baseline nobody owns any share of anything, and a zero would assert something the ledger has not said.

Two bounds are worth knowing. The holdings are **today's** holdings — there is no history of what a pot held when, so an earlier point means "what the pot's current contents were worth then", exactly as `?as_of_date=` already does. And the series never starts before the pot's **anchor**: its earliest ownership event, or its creation when the ledger is empty. Without that bound a pot created yesterday would report years of "the pot's value" for a pot that did not exist, because a shared investment brings its whole snapshot history with it. A back-dated opening moves the anchor earlier, which is right — that is the date the co-owners agreed their division began.

Holdings may leave a pot only while its ownership has **not** been agreed yet (`409 pot_already_divided`). Once a baseline exists, removing a holding would drop the pot's value by the whole of it while nobody's units change — every co-owner's share falling pro-rata so one person's private scope can gain it, with no cap on the amount. Taking value out of a divided pot is a withdrawal or a buy-out, both of which redeem units. Before the baseline there is nothing to take from anyone, which is what keeps undoing a mistaken move-in possible.

A holding must be your own private one to move it in, and naming one you cannot move refuses the **whole** request rather than moving the rest — a partial move would report success while some of what you named stayed put. An **account with linked entries cannot be shared at all** (`409 account_has_linked_entries`): its balance derives from expenses, income, settlements and transfers owned by one person, so a shared version would report a different figure to every member depending on whose rows they can see. Create a fresh account for the pot instead.

### The ownership ledger

Every balance is derived by replaying dated events — nothing is stored as a running total, which is also why back-dating is allowed here (it simply recomputes the series) while account reconciliation is forward-only.

| Method   | Path                                | Description                                                                                                                                          |
| -------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`    | `/pots/{id}/ownership`              | The full ledger in replay order. Visible to anyone who may see the pot, including a 0% owner.                                                        |
| `POST`   | `/pots/{id}/ownership/opening`      | Set the baseline. Body: `date`, `value`, `shares` (percentage per member id), optional `notes`. One event per owner.                                 |
| `POST`   | `/pots/{id}/ownership/movements`    | Record a `contribution` or `withdrawal`. Body: `type`, `date`, `member_id`, `amount`, optional account legs.                                         |
| `POST`   | `/pots/{id}/ownership/reagreements` | Move units between two members with no money. Body: `date`, `from_member_id`, `to_member_id`, and the share as either `percentage` or `whole_share`. |
| `DELETE` | `/pots/{id}/ownership/{event_id}`   | Delete an event; the series recomputes without it. An **opening** takes the whole baseline with it.                                                  |

**Deleting an opening deletes the whole baseline** — every one of its rows, not just the one named. The baseline is a division recorded as one event per owner, so half of it is a share nobody agreed to: delete one row of a 60/40 pot and it reads 100/0, and it cannot be repaired, because a second opening is refused while any of the first survives and the only way back would be a re-agreement, which records a gift that never happened. Every later movement is kept — and because a baseline is only ever the _first_ entry, a new one can be recorded only once nothing else is on the ledger. That is also why `pot_already_opened` describes ownership history rather than an opening: a pot can reach it with no opening on record at all.

A **re-agreement** must name two different members (`400 pot_reagreement_same_member`), and the movements endpoint records only a `contribution` or a `withdrawal` — an opening and a re-agreement take different inputs and have their own endpoints (`400 pot_unsupported_movement`).

The **opening** is the division every later percentage derives from, and it is only ever the FIRST entry on the ledger (`409 pot_already_opened` once anything is on it — a second baseline, or a movement that survived the first being deleted). Its percentages must total 100 (`400 pot_percentages_must_total_100`) and are never silently rescaled — quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it. Units are issued at a nominal 1.00, so the opening unit count reads back as the percentage entered.

A **movement** carries `from_account_id` / `to_account_id`, and those are what make it a real movement rather than a note about one: a contribution debits your private account and credits one the pot holds, so both balances stay right and the pot's value moves with the money. Both legs are optional (money can arrive from outside Renly, or land in an investment rather than a tracked account). The private leg must be your own account; the pot leg must belong to that pot. A cross-currency move stores **both** amounts and never a derived rate: `amount` + `amount_currency` for what left, `base_amount` for what was credited (`400 pot_base_amount_required` when the currencies differ and it is missing — deriving it would mean storing a rate).

**Each leg must be in the currency of the figure that moves its balance**, and the two are different columns: the pot leg's is `base_amount`, so it must be in the pot's base currency; the private leg's is `amount`, so it must be in `amount_currency` (`400 account_currency_mismatch` either way). Without both halves a movement could subtract an ARS figure from a USD account.

**The pot-side leg cannot be an archived account** (`400 pot_movement_account_inactive`). An archived holding is excluded from the pot's value but not from its own balance, so crediting one would move the account and leave the NAV where it was — issuing units against a value that never rises and diluting every other owner for nothing. The private leg has no such coupling and is allowed either way, exactly as a transfer's is.

**A movement must be dated on or after the opening date of every account it names** (`400 pot_movement_before_account_opened`). Each account's balance is bounded below by its own opening date — `opening_balance` already _is_ the balance then — so an earlier movement would issue or redeem units while the account it supposedly moved the money through never changed: value appearing in the pot from nowhere. It is the same rule `transfer_before_account_opened` enforces, and it matters more here because units are issued against it.

Movements are refused rather than guessed in three cases: no baseline yet (`400 pot_not_opened`), no known value on that date (`400 pot_valuation_required` — the pot cannot be priced, so the flow asks for its value first), and a withdrawal or re-agreement larger than the member actually holds (`400 pot_insufficient_units`). A pot valued at zero or less has no honest price to issue units against and is refused the same way.

**Taking or moving a member's WHOLE share is its own input, not a figure you compute.** A withdrawal derives its units by dividing money by the unit price, and a re-agreement by multiplying a percentage back out over the units outstanding — so neither can express "exactly what that member holds". Asking for the share's own value as a withdrawal lands on the holder's balance only about one time in twenty; the rest split between being refused (`400 pot_insufficient_units`, for asking to take out precisely what you own) and leaving a residual. And a residual is not cosmetic: a replayed balance is dropped only when it is _exactly_ zero, so a millionth of a unit survives as a `0.00%` owner worth `0.00`, on every screen, for good.

So a withdrawal may set **`whole_share`** to redeem the member's balance exactly, and a re-agreement states its share as **either** `percentage` **or** `whole_share` — exactly one of the two, never both and never neither (`422` otherwise, because silently preferring one would discard a figure the caller sent). `whole_share` applies to a withdrawal only; a contribution issues units _from_ money and has no share to take the whole of (`422`).

On a whole-share withdrawal, `amount` still records what money actually moved and is not re-derived from the units. The two may honestly differ — someone may accept less than their share is worth in order to get out — and the event stores the `unit_price` it was taken at, so the ledger says which figure is which. Nobody else's units change either way: a withdrawal only ever redeems its own member's.

**A private expense or income cannot be paid from a shared account** (`400 private_entry_from_shared_account`). The money really leaves, so the pot's value drops and every co-owner's share falls with it. Record a withdrawal from the pot first, or record the purchase as a **shared expense** funded from that account — which is the same money moving, with the other owners' share of it recorded as a balance they can settle. For the same reason **a transfer must stay within one scope** (`400 transfer_cross_scope`): a transfer is net-worth-neutral by construction, which is only true when both legs sit on the same side of the boundary. Crossing it is a contribution or a withdrawal.

---

## Shared expenses, shared income and settle-up

The **flow** half of shared money. A pot divides what a household _holds_; this divides what it _spends and earns_, and the two never mix: a shared expense or a piece of shared income lives in its own tables and each member's share is read into their normal list rather than mirrored into it.

**The one rule everything rests on.** A shared expense records two figures per member — what they **consumed** (their share, which is their expense) and what they **fronted** (the money they actually put up). Both sum to the expense's total, so a member's balance is what they fronted minus what they used, and the group's balances sum to exactly **zero in every currency** by construction rather than by a rule anyone has to remember.

There is deliberately **no payer column**. Money can come from a **shared account**, in which case the pot's owners fronted it in their own ownership proportions and no single member is the payer — something one column could not say. Those proportions are read from the ownership ledger **at the expense's date and pinned onto the split rows**, because the ledger is replayed: derived on every read, a back-dated ownership event would silently rewrite a balance two people had already agreed on.

The response's `payer_member_id` / `payer_display_name` are derived from the **funding**, and are null for any shared-account expense — including a pot with exactly one owner, where that owner does front the whole amount. Naming them would say somebody paid personally for money that came out of the joint account.

A pot owner who has since **left the group** still fronts their share, and is deliberately not subject to the active-seat check a named participant or payer gets: a named seat is a choice being made now, while a pot owner is a fact already on the ownership ledger. Excluding them would leave the fronted figures short of the total. They hold a real position the remaining members can see and settle, exactly as a name-only member does.

| Method   | Path                                 | Description                                                                                              |
| -------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `GET`    | `/groups/{id}/expenses`              | The group's shared expenses, newest first, each with every member's position in it. Optional `currency`. |
| `POST`   | `/groups/{id}/expenses`              | Record one and divide it. Returns `201`.                                                                 |
| `PUT`    | `/groups/{id}/expenses/{expense_id}` | Replace it and its whole split set.                                                                      |
| `DELETE` | `/groups/{id}/expenses/{expense_id}` | Delete it with its splits. Returns `204`.                                                                |

**Body:** `date`, `amount`, `currency`, `split_method`, `splits` (one `{member_id, figure}` per participant), and optionally `category`, `notes`, `payer_member_id`, `paid_from_account_id`, `payment_method`, `credit_card_id`.

`figure` carries whatever the chosen method needs and nothing else — ignored by `equal`, an amount for `exact`, a weight for `shares`, a percentage for `percentage`. One field rather than three, because exactly one is ever meaningful.

**Every method's parts sum to the total exactly.** The rounding remainder is spread one cent at a time from the largest part down, so no member ever carries more than one minor unit of it — a split amount is money somebody owes and it accumulates across every expense a group records. `exact` amounts must already add up (`400 shared_split_total`) and `percentage` figures must total 100 (`400 shared_split_percentages`); neither is silently rescaled. `shares` are relative weights with no total to hit, but they may not be negative or all zero (`400 shared_split_shares`).

**`payer_member_id` says who fronted it; the funding fields say how.** They are separate questions: somebody can front a bill in cash with no tracked account, and an account can front one with no single member behind it. It is required except when the funding account belongs to a pot (`400 shared_expense_payer_required` otherwise) — joint money is fronted by that pot's owners, so naming one of them as well is refused rather than ignored (`400 shared_expense_shared_account_payer`), because silently dropping a field the user filled in is how a form records something other than what it showed.

An undivided pot cannot fund a shared expense (`400 shared_expense_funding_pot_not_divided`): with no ownership on record there is no honest answer to whose money it was, and inventing one would either assert a division nobody agreed or leave the balances not summing to zero. Nor can a pot belonging to another group (`400 shared_expense_funding_scope`), whose owners this group could never settle with.

A **private** account or card must belong to the named payer, and a placeholder member has neither — both answer `404`. The expense's currency must match its funding account's (`400 account_currency_mismatch`) and it cannot be dated before that account opened (`400 shared_expense_before_account_opened`), the same bound every other movement respects. An account leg and a card leg are exclusive: a card charge raises a liability now and draws cash later at settlement, so it never draws an account as well.

**What it moves.** The funding account falls by the **whole amount** — the money really left, and who owed whom afterwards is the splits' business, never the account's. A card leg raises that card's liability exactly as a private charge does, and flags any reconciled statement covering the date as stale. Each member's own share appears in their `/expenses` list (see below); nobody's share is written into `expense_entries`.

### Shared income

The mirror of the section above, with the two sides swapped. A piece of shared income records two figures per member — what they are **entitled to** (their share, which is their income) and what actually **reached them** — and both sum to the row's total, so the group's balances still sum to exactly **zero in every currency** by construction. An entitlement is a claim on the group; cash that has already arrived is the group having settled part of it, which is why the subtraction runs the other way from an expense's.

There is deliberately **no receiver column**, for exactly the reason there is no payer column: money can arrive in a **shared account**, in which case the pot's owners received it in their own ownership proportions and no single member holds it. Those proportions are read from the ownership ledger **at the row's date and pinned onto the split rows**, because the ledger is replayed. The response's `received_by_member_id` / `received_by_display_name` are derived from the **destination** and are null for any joint row — including a pot with exactly one owner, where that owner does receive the whole amount.

| Method   | Path                              | Description                                                                                                |
| -------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `GET`    | `/groups/{id}/income`             | The group's shared income, newest first, each row with every member's position in it. Optional `currency`. |
| `POST`   | `/groups/{id}/income`             | Record one and divide it. Returns `201`.                                                                   |
| `PUT`    | `/groups/{id}/income/{income_id}` | Replace it and its whole split set.                                                                        |
| `DELETE` | `/groups/{id}/income/{income_id}` | Delete it with its splits. Returns `204`.                                                                  |

**Body:** `date`, `amount`, `currency`, `split_method`, `splits` (one `{member_id, figure}` per participant), `destination`, and optionally `category`, `notes`, `source_investment_id`, `received_by_member_id`, `paid_to_account_id`. The split methods, their `figure` field and their exact-sum guarantee are identical to a shared expense's — the same code divides both.

**`destination` says where the money ended up, and it decides everything else.**

- **`joint`** — it landed in a shared account a pot holds, so the pot is worth more and **every owner's share rises in proportion**. No units are issued and nobody's percentage moves: pro-rata growth needs no ownership event at all, which is what unit accounting is for. `paid_to_account_id` is **required** and must name an account one of _this_ group's pots holds (`400 shared_income_joint_account_required`; `400 shared_income_destination_scope` for another group's), and naming a recipient as well is refused (`400 shared_income_joint_receiver`). An undivided pot is refused (`400 shared_income_destination_pot_not_divided`): with no ownership on record there is nobody to credit, and crediting nobody would leave the received figures short of the total.
- **`distributed`** — it reached one person, who then holds whatever exceeds their own share as a balance the others can settle. `received_by_member_id` is **required** (`400 shared_income_receiver_required`), and `paid_to_account_id` is optional — income handed over in cash still divides — but when given it must be that person's **own private** account. A pot's account there contradicts the destination and is refused by name (`400 shared_income_distributed_shared_account`) rather than as a bare "not found".

Money arriving from outside the household **crosses no scope boundary on the way in**, which is why neither destination is an ownership event: only money already inside a pot can leave one, and that is a withdrawal.

**`source_investment_id` drives the default split (F1) and is the row's label.** Picking a co-owned asset divides the income the way that asset is owned — rent from a property the group owns 60/40 is 60/40 income unless somebody says otherwise. It must be a holding of one of this group's pots (`400 shared_income_source_scope`): the source is stored on a row the whole group reads and its **name** is on the response, so a private holding named there would put it in front of people who cannot see it. Income from an asset of your own is private income, which is a different table. The FK is `ON DELETE SET NULL` — the money arrived whatever later happens to the asset — so `source_investment_name` is null both for a row that names none and for one whose asset sits in a pot this viewer may not see.

The default is applied by the **form**, not the API: what gets stored is always the split the request states, so a later change to who owns the asset never restates income the group already agreed on.

**What it moves.** The destination account rises by the **whole amount** — the money really arrived, and who owes whom afterwards is the splits' business, never the account's. The currency must match that account's (`400 account_currency_mismatch`) and the row cannot be dated before it opened (`400 shared_income_before_account_opened`). That FK is `ON DELETE SET NULL` too, and a joint row whose account is later deleted keeps saying it stayed joint: the money did stay together, and who was credited what is on the split rows, which the deletion does not touch. Naming an account is therefore a rule at write time rather than a permanent property of the row. Each member's own share appears in their `/income` list (see below); nobody's share is written into `income_entries`.

### Balances and settlements

| Method   | Path                                     | Description                                                                            |
| -------- | ---------------------------------------- | -------------------------------------------------------------------------------------- |
| `GET`    | `/groups/{id}/balances`                  | Every member's position per currency, plus the fewest payments that clear each bucket. |
| `GET`    | `/groups/{id}/settlements`               | Recorded settlements and write-offs, newest first.                                     |
| `POST`   | `/groups/{id}/settlements`               | Record a payment one member made to another. Returns `201`.                            |
| `POST`   | `/groups/{id}/settlements/preview`       | Dry run: where an overpayment would land. Writes nothing.                              |
| `POST`   | `/groups/{id}/settlements/waterfall`     | Record one payment across every bucket it reaches. Returns `201`.                      |
| `POST`   | `/groups/{id}/settlements/write-off`     | Give up on a debt. Returns `201`.                                                      |
| `PUT`    | `/groups/{id}/settlements/{sid}/account` | Attach or clear the caller's **own** cash leg.                                         |
| `POST`   | `/groups/{id}/settlements/{sid}/confirm` | Acknowledge receipt. Payee only.                                                       |
| `DELETE` | `/groups/{id}/settlements/{sid}/confirm` | Take the confirmation back. Payee only.                                                |
| `DELETE` | `/groups/{id}/settlements/{sid}`         | Remove it — which is what reversing one is. Returns `204`.                             |
| `GET`    | `/groups/{id}/money-settings`            | The group's default split method and auto-finalise setting.                            |
| `PUT`    | `/groups/{id}/money-settings`            | Change them. Admin only.                                                               |

**Balances never net across currencies.** Each currency is its own bucket, its own settle line and its own zero-sum: you can be owed pesos while owing dollars, and merging the two would invent a rate nobody agreed to. The converted figure beside a bucket is for reading at a glance and is never what anybody settles.

**Both flows land in the same bucket.** A member who fronted a dinner and a member who collected the rent are owed and owing in the same currency, so one plan nets them rather than asking for two payments. The two are read in opposite directions — an expense's position is fronted minus consumed, income's is entitled minus received — and one settlement or write-off clears whatever they add up to.

The settle-up plan pays the **largest creditor from the largest debtor** and repeats, so A pays C directly rather than A paying B who pays C. It is deterministic — the same balances always produce the same plan — and never needs more than one payment per member less one.

**A settlement carries up to three amounts.** `amount`/`currency` is the **bucket** leg: which balance it cleared, and by how much. `from_amount` is what actually left the payer's account in that account's currency, and `to_amount` what arrived in the payee's. Each cash figure is set **only when that side crossed currencies** — when they match, what left the account _is_ what cleared the bucket, so a second copy of the same figure would be a second thing to keep in step (`400 group_settlement_leg_amounts_must_match` if they disagree, `400 group_settlement_leg_amount_required` if they cross and nothing is stated). There is no stored rate: the pair of amounts _is_ the record of it.

**Each side records their own leg.** The two legs belong to two different people, and neither can see the other's accounts at all — the row-level policies hide them — so a request naming both is refused (`400 group_settlement_foreign_leg`) rather than answering a bare "not found". The payer usually names theirs when recording the payment; the payee attaches theirs through `PUT …/account` when they confirm receiving it. Both legs are optional: mark-as-paid with no account named is the default, and a name-only member has no account to name.

**A pending settlement already counts against the balance** — the money really moved, and confirming it is an acknowledgement rather than a gate on the arithmetic. What confirmation changes is who may undo it: while pending, either named member may delete it (which is what reversing one is); once confirmed, nobody can until the **payee** un-confirms it (`409 group_settlement_confirmed`), because undoing it silently would overwrite somebody else's word. Only the payee may confirm or un-confirm (`403 group_settlement_not_payee`). A group can opt into `auto_finalise_settlements`, which confirms on the spot.

**Overpaying spills across buckets, but never silently.** A payment larger than the bucket it names has an excess, and if the payer owes the payee in other currencies the excess can clear those too. `POST …/preview` returns the plan — one entry per reachable bucket, largest-cost first, each priced in the currency being paid — and writes nothing; `POST …/waterfall` records it. Both take the same body, and the write **recomputes the allocation from it**: the request names which buckets the payer kept (`spillover_currencies`), never how much to put in them, so no client can clear a bucket at a rate nobody agreed to. Omitting the field means every reachable bucket; an empty list means none of them, which is a real answer and not the same thing.

The conversion uses the rate in force on the **payment's date**, not today's — a payment happened on a day, and that is the rate at which the money actually moved. (A displayed balance converts at today's, deliberately: it is a live position with no single date behind it.) A bucket with no usable rate is named in `skipped_currencies` and left alone rather than guessed at.

**Where the money goes.** Each bucket the excess reaches gets its own settlement in **its own** currency, because balances never net; one payment therefore writes several rows, together or not at all. Anything the ticked buckets did not absorb is a `leftover`, which the paid bucket carries — so it flips by exactly that much and the cash reconciles: the rows' costs plus the leftover are the payment, to the cent. With nothing ticked the leftover is the whole excess and this is a single overpaying settlement, which is the behaviour without a waterfall at all.

**One real payment, one cash leg, split across the rows.** The payer states what left their account once; it is divided between the rows in proportion to what each consumed of the payment, and the parts sum to the stated total exactly. A row whose bucket is already in the account's own currency crosses nothing, so it moves exactly what it clears and the rows that _did_ cross split what is left — a proportional share there would claim the account paid, say, 8.58 dollars to clear a 10-dollar bucket.

**A write-off** clears the same bucket a payment would and moves no money at all, so it names no account (`409 group_settlement_write_off_has_no_leg`). Only the creditor may record or remove one (`403 group_settlement_not_creditor`): giving up a claim is theirs to give up, and the other way round would be one person deciding on somebody else's behalf. It is the other exit, besides settling, that clears a balance — and one of them is required before a member with an open balance can be removed from the group or delete their account (`409 group_balance_outstanding`). Unlike a payment it is **capped at the balance** (`400 group_write_off_exceeds_balance`): an overpaying payment is legal and flips the bucket, because real money moved and the payee owes some back, but forgiving more than you are owed would leave the person you forgave owed money by you, out of nothing.

### Your share in `/expenses` and `/income`

`GET /expenses` returns one list spanning two tables: the caller's own `expense_entries` rows and their **share** of every shared expense their group seats take part in. One list rather than two because "what did I spend" has one answer, and a share of a group dinner is spending exactly as much as a solo one. The share is read at query time and never mirrored, so an edit to the group's expense has nothing to chase.

Each row carries **`scope`** (`private` | `shared`), and that is half its identity rather than a label: ids are unique **per table and not across them**, so a shared row's `id` means nothing to `/expenses/{id}` and every client acting on a row must gate on the scope. A shared row additionally carries `group_id`, `group_name` and `full_amount` — the whole expense, of which `amount` is the caller's share — while `account_id` and `credit_card_id` are `null`, because those identify the _payer's_ instrument, frequently another member's.

A split of **zero** never appears: it is a payer who took no part, which is a real position in the expense but not spending. Every filter and sort applies across both halves of the list, and paging is stable because the order breaks ties on `(id, scope)` rather than on `id` alone.

`GET /income` does exactly the same for the income half, field for field: `scope`, `group_id`, `group_name` and `full_amount` on a shared row, `account_id` null on it (it identifies where the money _landed_, frequently another member's account or a pot's), the same `(id, scope)` tie-break, and the same rule that a shared branch is not built at all for a caller in no group. The zero it drops is the mirror one — a **collector entitled to nothing**, who holds a real position in the row but earned none of it.

Neither list is writable through its shared rows. A shared row's id belongs to another table, so `PUT`/`DELETE` on `/expenses/{id}` or `/income/{id}` with it would act on whatever private entry happens to hold that number; the group's own endpoints are where those rows are edited.

---

## Notifications

What Renly tells you about, and where it reaches you. Three channels — the in-app feed, email, and web
push — with a switch per event per channel.

A notification stores its **event** and a **payload**, never a rendered sentence. The prose is built by
the client from its own translations, so the feed reads in whatever language you are using now and a
copy fix reaches notifications written months ago. The payload also carries the ids the client builds
the row's link from, so no route is stored. Email and web push are the exception and are rendered
server-side, for the same reason transactional emails are: there is no client to render them at the
moment they are sent, so they are localized to your stored language.

**Events.** `group_invited`, `member_joined`, `ownership_changed` (a pot's first division, or a change
of split), `pot_movement` (money in or out of a pot), `snapshot_due` (a pot is behind on its valuation
cadence), `settle_marked_paid`, `settle_confirmed`, `balance_written_off`, `shared_expense_added`,
`shared_income_added`.

**Defaults.** The feed is on for every event. Email and push are on for the five about your own money
or awaiting your own action — `ownership_changed`, `snapshot_due`, `settle_marked_paid`,
`settle_confirmed`, `balance_written_off` — and off for the rest, so a household recording ten expenses
a week does not send ten emails to everyone in it. A preference row exists only where you have
overridden a default, so a new event has an answer for every existing account the day it is added.

**A push carries no figures.** It renders on a lock screen, where anybody holding the phone reads it, so
it says who did what in which group and the amount waits for the app. The feed and the email carry the
figure.

| Method   | Path                                | Description                                                                                                                                                                           |
| -------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`    | `/notifications`                    | One page of your notifications, newest first, with `total` and `unread`. Optional `limit` (1–50, default 20) and `offset`.                                                            |
| `POST`   | `/notifications/{id}/read`          | Mark one read. `404` for an id that is not yours — indistinguishable from one that does not exist.                                                                                    |
| `POST`   | `/notifications/read-all`           | Mark every notification you can see read. Returns how many changed.                                                                                                                   |
| `GET`    | `/notifications/preferences`        | The whole grid: every event on every channel, with `is_default` saying which cells you have never touched. Also `push_available` and the `push_public_key` a browser subscribes with. |
| `PUT`    | `/notifications/preferences`        | Set one switch (`event`, `channel`, `enabled`) and get the whole grid back. One cell per request, so two tabs editing different rows cannot overwrite each other.                     |
| `POST`   | `/notifications/push/subscriptions` | Register this browser for web push (`endpoint`, `p256dh`, `auth`, optional `user_agent`). `409 push_not_configured` where the deployment has no VAPID key.                            |
| `DELETE` | `/notifications/push/subscriptions` | Stop pushing to one browser, named by its `endpoint` in the body. Idempotent.                                                                                                         |

**Web push needs no third-party service.** The browser's own push service is the endpoint and VAPID is
how it knows the message is from Renly; a deployment with no key configured reports `push_available:
false` and offers no switch rather than storing a subscription nothing would ever reach. Subscriptions
are per BROWSER, not per account — a laptop and a phone are two decisions — and a subscription the push
service reports gone is deleted on the spot rather than retried forever. The `p256dh` and `auth` keys
are write-only: no endpoint reads them back, and they are excluded from the data export, exactly as
session credentials are.

**The overdue-valuation reminder.** `snapshot_due` is the one event nobody triggers: an hourly job
reports a pot whose valuation has fallen behind the cadence its group agreed on, to the members who can
actually re-value it. Each person is reached at 09:00 in their own timezone and at most once per cadence
period — a pot still overdue when the next period opens raises it again.

---

## Feedback

The in-app feedback channel. Any authenticated user can submit feedback; the caller's account email is attached server-side (not part of the body), and every admin is notified by email best-effort (a mail outage never fails the submission). Listing all feedback is admin-only.

| Method | Path        | Description                                                                                                                                 |
| ------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST` | `/feedback` | Submit feedback. Body: `category` (`bug` \| `idea` \| `question` \| `other`), `message` (1–2000 chars). Returns `201` with the created row. |
| `GET`  | `/feedback` | List all submitted feedback, newest first, each with the author's email. Admin only (`403` otherwise).                                      |

---

## Metrics

All metric endpoints support currency conversion via the `currency` query parameter. Pass `currency=ARS` to see values in Argentine pesos, `currency=USD` for US dollars, etc. Omit it to see values in each investment's original currency. The code is case-insensitive (`usd` and `USD` are equivalent).

Most endpoints also accept these common filters:

| Parameter        | Type   | Description                                |
| ---------------- | ------ | ------------------------------------------ |
| `currency`       | string | Display currency for conversion.           |
| `investment_ids` | int[]  | Limit to specific investments.             |
| `collection_ids` | int[]  | Limit to investments in these collections. |
| `category`       | string | Limit to a specific category.              |
| `search`         | string | Filter by investment name.                 |
| `start_date`     | date   | Start of date range (YYYY-MM-DD).          |
| `end_date`       | date   | End of date range (YYYY-MM-DD).            |

| Method | Path                                | Description                                                                                           | Supports date range       |
| ------ | ----------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------- |
| `GET`  | `/metrics/portfolio`                | Portfolio-level metrics: total value, invested capital, gain/loss, TWR, IRR, month-over-month change. | Yes                       |
| `GET`  | `/metrics/portfolio/evolution`      | Monthly portfolio value series for the evolution chart.                                               | Yes                       |
| `GET`  | `/metrics/investment/{id}`          | Detailed metrics for a single investment: TWR, IRR, period returns.                                   | No (uses `currency` only) |
| `GET`  | `/metrics/allocation`               | Portfolio allocation by investment category (percentage breakdown).                                   | No                        |
| `GET`  | `/metrics/allocation/by-collection` | Portfolio allocation by collection (percentage breakdown).                                            | No                        |
| `GET`  | `/metrics/investments/summary`      | Compact per-investment metrics for the dashboard table: value, return, change.                        | Yes                       |

---

## Exchange Rates

| Method | Path                         | Description                                                                                                   |
| ------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/exchange-rates/latest`     | Latest available rate for each currency pair.                                                                 |
| `GET`  | `/exchange-rates`            | Rates for a specific date. Requires `date` query parameter (YYYY-MM-DD).                                      |
| `GET`  | `/exchange-rates/currencies` | Currency codes with exchange-rate support (`{ "currencies": [...] }`), sorted. Drives the entry-form pickers. |

**Available pairs:** USD/ARS (oficial), USD/ARS (MEP), USD/ARS (blue), USD/BRL, USD/EUR, USD/GBP.

**Supported currencies & fail-loud conversion:** Only `ARS`, `BRL`, `EUR`, `GBP`, `USD` have exchange-rate support. `POST`/`PUT` on every finance-entry type — expenses, income, subscriptions, installments, and payment obligations — reject any other `currency` with **422**. When a conversion to the requested display currency has no stored rate, the value is **skipped, never converted at par**: aggregate responses (dashboards, finance metrics, expense/income lists, payments calendar) carry an additive `skipped_currencies` list of the excluded codes; per-row `converted_*` fields stay `null`. A snapshot or transaction whose `currency` differs from its investment's `base_currency` is rejected with **400** (`Currency <X> does not match the investment's base currency (<Y>).`).

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

Every error response has a JSON body with a human-readable `detail` (English) and a stable machine-readable `code` (e.g. `not_found`, `invalid_credentials`, `has_linked_expenses`); some carry extra context fields (e.g. `installment_locked_field` includes `fields`). The `code` is locale-independent — clients map it to their own localized message and fall back to `detail`. The HTTP status is one of:

| Code  | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `400` | Bad request -- e.g., a snapshot/transaction `currency` that doesn't match its investment's `base_currency` (`investment_currency_mismatch`), an invalid transfer (`transfer_same_account`, `transfer_amounts_must_match`, `transfer_amount_required`), a group-invite link that is unknown, already used or expired (`invalid_token`), an ownership movement that cannot be priced, afforded or placed (`pot_not_opened`, `pot_valuation_required`, `pot_insufficient_units`, `pot_percentages_must_total_100`, `pot_reagreement_same_member`, `pot_unsupported_movement`, `pot_base_amount_required`, `pot_movement_before_account_opened`, `pot_movement_account_inactive`), a flow crossing a scope boundary (`private_entry_from_shared_account`, `transfer_cross_scope`), a shared expense that does not divide, is funded from money nobody has divided, or does not say who fronted it (`shared_split_total`, `shared_split_percentages`, `shared_split_shares`, `shared_split_no_participants`, `shared_expense_payer_required`, `shared_expense_shared_account_payer`, `shared_expense_funding_pot_not_divided`, `shared_expense_funding_scope`, `shared_expense_before_account_opened`), shared income whose destination contradicts where the money landed or whose source is not the group's (`shared_income_receiver_required`, `shared_income_joint_receiver`, `shared_income_joint_account_required`, `shared_income_distributed_shared_account`, `shared_income_destination_scope`, `shared_income_destination_pot_not_divided`, `shared_income_source_scope`, `shared_income_before_account_opened`), a settlement whose cash legs do not add up or name the wrong side (`group_settlement_same_member`, `group_settlement_leg_without_account`, `group_settlement_leg_amount_required`, `group_settlement_leg_amounts_must_match`, `group_settlement_foreign_leg`, `group_settlement_before_account_opened`), a reconciliation dated in the future or before its account opened (`account_reconciliation_future_date`, `account_reconciliation_before_opening`), a settlement dated before its funding account opened (`settlement_before_account_opened`), a reconciliation whose period bounds are inconsistent, such as a start after its end (`reconciliation_period_mismatch`), a `credit_card_id` sent without `payment_method: credit_card` (`payment_pairing`), a password found in a known breach at registration (`password_breached`), or an import file that isn't readable as one (`invalid_import_file`). |
| `401` | Unauthorized -- missing or invalid access token (`invalid_auth_token`), wrong credentials at login (`invalid_credentials`), or a refresh token that is unknown, expired, revoked, already used, or older than the session it belongs to (`invalid_refresh_token`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `402` | Payment required -- the action needs a plan the account does not have (`plan_required`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `403` | Forbidden -- an admin-only action attempted by a plain member (`group_admin_required`), an account-administration action attempted by a non-admin (`admin_required`), a write to a pot you may only read (`pot_write_required`), confirming a settlement you did not receive or writing off a debt you are not owed (`group_settlement_not_payee`, `group_settlement_not_creditor`), an unverified email at login (`email_not_verified`), or a signup attempt with an invite link that is not valid (`invalid_invite`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `404` | Not found -- the resource doesn't exist or doesn't belong to you. A group you aren't a member of answers `404` too, so it can't be told apart from one that doesn't exist.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `409` | Conflict -- e.g., trying to change an investment's currency when it already has snapshots, changing an account's currency or opening date once entries link to it, editing or deleting an expense/income row that a reconciliation owns (`reconciliation_owned_entry`), a change that would leave a group with no admin (`group_last_admin`), a second seat claimed in one group (`group_membership_exists`), an invite to a seat already claimed (`group_seat_taken`), deleting a pot that still holds something (`pot_has_holdings`), a baseline recorded when the ledger is not empty (`pot_already_opened`), taking a holding out of a pot whose ownership is already agreed (`pot_already_divided`), sharing an account that already has linked entries (`account_has_linked_entries`), editing or removing a settlement the payee has confirmed (`group_settlement_confirmed`), attaching an account to a written-off balance (`group_settlement_write_off_has_no_leg`), removing a member or deleting an account while a group balance is still open (`group_balance_outstanding`), inviting an email that already has an account (`invite_email_taken`), or a partial UNIQUE INDEX rejection on the expense entries table (manual entry duplicating a scheduler-emitted row for the same subscription / installment on the same date).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `422` | Validation error -- the request body is malformed or missing required fields, a finance-entry `currency` (expense/income/subscription/installment/payment obligation) outside the supported set (`ARS`, `BRL`, `EUR`, `GBP`, `USD`), or a category reserved for the system (the reconciliation adjustment categories).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `503` | Service unavailable -- an external service is temporarily unreachable: a price provider, or exchange rates with no stored rate for the currency asked for (`exchange_rate_unavailable`, which single-investment metrics raise rather than silently dropping the conversion).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
