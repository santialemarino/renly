# Renly — Architecture Document

> Version 1.5 — March 2026
> This document describes in detail the architecture, technology decisions, data model, and structure of the application. It is intended to be read by a developer (human or AI agent) who needs to implement the project from scratch.

---

## 1. Product Vision

Renly is a personal web-based financial management app, initially focused on **investment tracking**, with an architecture ready to expand into income/expense management, recurring subscriptions, and installment payments.

### Target Users

- 2 to 3 users (family/partner use)
- Not a public or large-scale multi-tenant app
- All users are trusted and share a single "family account"

### Core Product Values

1. **Fast data entry**: the user shouldn't spend more than 15-20 minutes per month entering data
2. **Visual clarity**: better than Excel, with actionable and easy-to-read metrics
3. **Reliability**: numbers must always be correct
4. **Extensibility**: the investment MVP must be able to grow without breaking anything

---

## 2. Project Phases

| Phase       | Name                | Description                                                                         |
| ----------- | ------------------- | ----------------------------------------------------------------------------------- |
| **MVP**     | Investments         | Investment CRUD, monthly snapshots, dashboard with metrics, ARS/USD currency switch |
| **Phase 2** | Money Flow          | Income by category (salary, rent, dividends), one-off expenses by category          |
| **Phase 3** | Structured Expenses | Active/inactive subscriptions, installment payments, monthly budgets, alerts        |
| **Phase 4** | Automation          | Scraping / integration with Cocos Capital, Mercado Pago, home banking, brokers      |

---

## 3. Technology Stack

### 3.1 Frontend — Next.js 14+ (App Router)

**Why Next.js?**

- The most mature React framework with the best ecosystem in 2025
- App Router provides nested layouts, loading states, and server components out of the box
- Trivial deployment on Vercel with automatic CI/CD from Git
- Excellent first-class TypeScript support

**Key libraries:**

| Library                | Role                     | Justification                                                                                      |
| ---------------------- | ------------------------ | -------------------------------------------------------------------------------------------------- |
| `shadcn/ui`            | UI components            | High quality, accessible, easily customizable; code lives in the repo (not a black-box dependency) |
| `Tailwind CSS`         | Styling                  | Utility-first, consistent, fast to iterate                                                         |
| `Tremor` or `Recharts` | Charts                   | Tremor is purpose-built for financial dashboards; Recharts for more control                        |
| `TanStack Query`       | Data fetching            | Cache, revalidation, automatic loading/error states                                                |
| `TanStack Table`       | Data tables              | Best solution for complex tables with sorting, filtering, pagination                               |
| `Zustand`              | Lightweight global state | For the global currency switch and UI preferences                                                  |
| `NextAuth.js`          | Authentication           | See section 3.5                                                                                    |
| `Zod`                  | Form validation          | Shared with backend for schema coherence                                                           |

### 3.2 Backend — Python with FastAPI

**Why Python/FastAPI and not Go or Node?**

- For financial calculations (IRR, CAGR, time-weighted return, percentage changes) Python has the richest ecosystem: `pandas`, `numpy`, `scipy`
- FastAPI is the most modern Python framework: native async, automatic Swagger docs, typed with Pydantic
- Go would be more performant, but the app has no scale requirements that would justify it; Python development productivity is higher
- Node could work, but mixing TypeScript in front and back would complicate the monorepo without real benefit since the backend needs numerical computation capabilities

**Key libraries:**

| Library            | Role                                                |
| ------------------ | --------------------------------------------------- |
| `FastAPI`          | Async web framework                                 |
| `SQLModel`         | ORM (see section 3.3)                               |
| `Pydantic v2`      | Validation and serialization (included in SQLModel) |
| `Alembic`          | Database migrations                                 |
| `asyncpg`          | Async PostgreSQL driver                             |
| `pandas` / `numpy` | Financial calculations                              |
| `httpx`            | Async HTTP client (for exchange rate APIs)          |
| `APScheduler`      | Scheduled jobs (exchange rate updates)              |

### 3.3 ORM — SQLModel

**Why SQLModel and not plain SQLAlchemy or raw queries?**

SQLModel was created by the same author as FastAPI and is specifically designed to work with it. The core advantage is that **a single model serves three purposes**:

```python
class Investment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    category: InvestmentCategory
    base_currency: Currency
    user_id: int = Field(foreign_key="user.id")
```

This same model is:

1. The PostgreSQL table (with `table=True`)
2. The API validation schema (Pydantic)
3. The TypeScript type that can be generated via codegen

Plain SQLAlchemy requires defining models and schemas separately. For a project with no legacy code, SQLModel significantly reduces boilerplate.

### 3.4 Database — PostgreSQL on Supabase

**Why Supabase only as DB hosting?**

- Supabase provides free managed PostgreSQL to start
- Used **only as hosting** — Supabase Auth and the Supabase API are not used
- This simplifies the architecture: FastAPI backend is the only service that talks to the DB
- Migrating to another provider (Railway, Neon, etc.) in the future is trivial

### 3.5 Authentication — NextAuth.js (Auth.js v5)

**Why NextAuth and not Supabase Auth?**

- The app has a small number of trusted users; no complex public OAuth flows are needed
- NextAuth with `credentials provider` is simpler: username + hashed password in DB, JWT sessions
- The team already has experience with NextAuth in a similar monorepo context (company project)
- That implementation can be reused directly

**Implementation:**

- Users stored in `users` table in PostgreSQL with `password` hashed with `bcrypt`
- Sessions managed with signed JWTs, configurable expiration
- Frontend sends the token on each request to FastAPI backend
- FastAPI validates the JWT in a shared middleware

**Security note:** never store passwords in plain text. Use `bcrypt` with a salt factor >= 12.

---

## 4. Infrastructure and Deployment

| Service        | Platform                         | Initial Tier | Estimated Cost                 |
| -------------- | -------------------------------- | ------------ | ------------------------------ |
| Frontend       | **Vercel**                       | Hobby (free) | $0 — $20/mo on Pro             |
| Backend API    | **Railway**                      | Starter      | ~$5-10/mo                      |
| Database       | **Supabase**                     | Free tier    | $0 — $25/mo if limits exceeded |
| Exchange rates | **bluelytics API** + public APIs | Free         | $0                             |

**CI/CD:**

- Each push to `main` triggers automatic deployment on Vercel (frontend) and Railway (backend)
- Railway detects the `Dockerfile` or `railway.toml` in `apps/api`
- Environment variables managed on each platform, never in the repo

**Local development:**

- `docker-compose.yml` at the root spins up PostgreSQL and the backend
- Frontend runs with `next dev` pointing to the local backend

---

## 5. Monorepo Structure

```
renly/
├── apps/
│   ├── web/                    # Next.js App Router
│   │   ├── app/
│   │   │   ├── (auth)/         # Login, registration
│   │   │   ├── dashboard/      # Main view
│   │   │   ├── investments/    # Investment CRUD
│   │   │   ├── data-entry/     # Monthly data entry
│   │   │   └── settings/       # Account settings
│   │   ├── components/
│   │   │   ├── ui/             # shadcn/ui components
│   │   │   ├── charts/         # Tremor/Recharts wrappers
│   │   │   └── investments/    # Investment-specific components
│   │   └── lib/
│   │       ├── api/            # Fetch wrappers for backend
│   │       ├── auth/           # NextAuth configuration
│   │       └── utils/          # Currency formatting, dates, etc.
│   │
│   └── api/                    # FastAPI
│       ├── app/
│       │   ├── models/         # SQLModel models
│       │   ├── routers/        # Endpoints by domain
│       │   ├── services/       # Business logic and metrics
│       │   ├── deps/           # Dependencies (auth, DB session)
│       │   └── main.py
│       ├── migrations/         # Alembic
│       └── tests/
│
├── packages/
│   └── types/                  # Shared TypeScript types
│
├── turbo.json
├── docker-compose.yml
├── .env.example
└── README.md
```

**Why Turborepo?**

- Manages build and dev for multiple apps in a single repo with intelligent caching
- Allows running `turbo dev` from the root to start both frontend and backend simultaneously
- In the future, if a mobile app is added (React Native), it's added as `apps/mobile` without changing anything else

---

## 6. Data Model

### Core Currency Design Principle

All transactions and snapshots are stored in their **original currency**. Conversion to ARS or USD is done at query time using the `exchange_rates` table. This ensures no information is ever lost and that the currency switch in the dashboard is always accurate.

### ER Diagram

See also `apps/api/database/01_create_tables.sql` for the full creation script.

```
+------------------+         +------------------------+
|      users       |         |      investments       |
+------------------+         +------------------------+
| id (PK)          |<----+   | id (PK)                |
| name             |     |   | name                   |
| email (unique)   |     +---| user_id (FK)           |
| password_hash    |         | category               |
| created_at       |         | base_currency          |
| updated_at       |         | broker                 |
+------------------+         | notes                  |
                              | is_active              |
                              | created_at             |
                              +-----------+------------+
                                          |
              +---------------------------+---------------------------+
              |                           |                           |
              v                           v                           v
+------------------------+  +-----------------+  +---------------------+
|  investment_snapshots  |  |  transactions   |  |  investment_targets |
+------------------------+  +-----------------+  +---------------------+
| id (PK)                |  | id (PK)         |  | id (PK)             |
| investment_id (FK)     |  | investment_id   |  | investment_id (FK)  |
| date                   |  | (FK)            |  | target_percentage   |
| value                  |  | date            |  | notes               |
| currency               |  | amount          |  +---------------------+
| notes                  |  | currency        |
+------------------------+  | type            |
                             | notes           |
                             +-----------------+

+-----------------------------+
|       exchange_rates        |
+-----------------------------+
| id (PK)                     |
| date                        |
| pair                        |
| rate                        |
| source                      |
+-----------------------------+
```

### Table Descriptions

**`users`** — App user table. Passwords hashed with bcrypt. Very few records (2-3).

**`investments`** — Each investment the user has or had. A stock, a term deposit, a dollar position, a mutual fund, etc. `base_currency` is the currency in which that investment is naturally measured (e.g., CEDEARs -> USD, term deposit -> ARS).

**`investment_snapshots`** — The total value of an investment at a given point in time (typically end of month). Equivalent to the "monthly column" in the original Excel. The `UNIQUE (investment_id, date)` constraint guarantees one snapshot per month per investment.

**`transactions`** — Every capital movement: buy, sell, additional deposit. Critical to distinguish whether an investment grew because it went up or because more capital was deposited — exactly the problem the second row in the Excel was solving.

**`exchange_rates`** — Historical exchange rate by pair and date. Auto-updated via scheduled job (bluelytics API). Enables correct historical conversion. Pairs: `USD_ARS_OFICIAL`, `USD_ARS_MEP`, `USD_ARS_BLUE`.

**`investment_targets`** _(optional in MVP)_ — Target allocation percentage per investment. Useful for showing in the dashboard whether the user is over or under-exposed in a given category.

**`investment_groups`** _(MVP)_ — Named groups for aggregating investments (e.g. "Retirement", "Kids", "Trading"). User-defined; one user can have many groups.

**`investment_group_members`** _(MVP)_ — Many-to-many: an investment can belong to zero, one, or several groups. Enables filtering and dashboard views “by group” in addition to by category.

```sql
-- Suggested schema addition
CREATE TABLE investment_groups (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name          VARCHAR(255) NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE investment_group_members (
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  group_id      BIGINT NOT NULL REFERENCES investment_groups(id) ON DELETE CASCADE,
  PRIMARY KEY (investment_id, group_id)
);
```

**`user_settings`** _(MVP)_ — Per-user app configuration. Used for display preferences that drive the global currency switch and future options. MVP stores which currencies are enabled for the switch and their order; the page can be expanded later (default period, theme, etc.).

```sql
-- Suggested schema addition (key-value or single JSON column)
CREATE TABLE user_settings (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
  settings   JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- e.g. settings: { "display_currencies": ["USD", "ARS"], "default_currency": "USD" }
```

---

## 7. API — Main Endpoints

### Authentication

```
POST   /auth/register       -> create user, JWT token (201)
POST   /auth/login          -> JWT token
POST   /auth/logout         -> 204
GET    /auth/me             -> current user
```

### Investments

List endpoint is **server-side only**: search, filters, and pagination are applied in the backend. Every change (search text, group/category filter, page) triggers a new request; the client never loads the full list for filtering.

```
GET    /investments                         -> list; query params: search, group_ids[], category, page, page_size, active_only
POST   /investments                         -> create investment (201)
GET    /investments/{id}                    -> detail
PUT    /investments/{id}                    -> edit
DELETE /investments/{id}                    -> soft delete (204)

GET    /investments/{id}/snapshots          -> value history
POST   /investments/{id}/snapshots          -> create or update snapshot (upsert by date)

GET    /investments/{id}/transactions       -> transaction history
GET    /investments/{id}/transactions/{tx_id} -> one transaction
POST   /investments/{id}/transactions       -> add transaction (201)
PUT    /investments/{id}/transactions/{tx_id} -> update transaction
DELETE /investments/{id}/transactions/{tx_id} -> delete transaction (204)
```

### Groups (MVP)

```
GET    /groups                     -> list user's groups (with member count or ids)
POST   /groups                     -> create group (201)
GET    /groups/{id}                -> group detail + investment ids
PUT    /groups/{id}                -> edit group name
DELETE /groups/{id}                -> delete group (204)
PUT    /groups/{id}/investments    -> set membership (body: investment_ids[])
# Or: POST/DELETE /groups/{id}/investments/{investment_id} for add/remove
```

### Settings (MVP)

```
GET    /settings             -> current user's settings (e.g. display_currencies, default_currency)
PUT    /settings              -> update user settings (partial; body: display_currencies[], default_currency, ...)
```

### Metrics (calculated in backend with pandas)

```
GET    /metrics/portfolio              -> global portfolio metrics
GET    /metrics/portfolio?currency=USD -> with currency conversion
GET    /metrics/investment/{id}        -> metrics for a specific investment
GET    /metrics/allocation             -> distribution by category
```

### Exchange Rates

```
GET    /exchange-rates/latest          -> current rates
GET    /exchange-rates?date=2026-03    -> historical rate
```

---

## 8. Dashboard Metrics

### Main Panel (Portfolio Overview)

The dashboard has a left sidebar with the navigation sections: Dashboard, Investments, Data Entry, and Settings. In the top-right corner there is a global currency selector (ARS / USD) and the user's name with access to the profile menu.

The main area is organized in three vertical blocks:

**Top block — metric cards:** three cards in a row showing the current total portfolio value in the selected currency, the total historical return as a percentage, and the change versus the previous month in absolute value. Each card has a color indicator (green/red) based on the direction of the change. There is a period selector (last month, last 3 months, YTD, all time).

**Middle block — evolution chart:** a line chart with months on the X axis and portfolio value on the Y axis, displayed in the globally selected currency. If there are multiple years of data, the user can navigate between years or switch to a multi-year view.

**Bottom block — two columns:** on the left, a pie or donut chart showing portfolio distribution by category (CEDEARs, FCI, Dollars, Bonds, etc.) with each one's percentage. On the right, a compact table listing each investment with its current value, monthly percentage change, and an up/down/flat arrow indicator.

**Search and drill-down:** A search/filter bar allows narrowing the dashboard to a specific investment, a **group** (see §6 and §11.2), or a **category/type**. The search is smart: it shows matches for investments by name, groups by name, and categories. Selecting an investment, group, or category navigates to a “filtered dashboard” view with the same layout (cards, chart, distribution) but metrics and series computed only for that selection. Back returns to the previous context (e.g. full dashboard or investments table).

### Calculated Metrics

| Metric                 | Formula / Description                                              |
| ---------------------- | ------------------------------------------------------------------ |
| **Current value**      | Latest snapshot for each investment converted to selected currency |
| **Invested capital**   | Sum of all DEPOSIT/BUY minus WITHDRAWAL/SELL (net capital in)      |
| **Period return**      | See §8.1: `(S_curr - NetCF) / S_prev - 1` between two snapshots    |
| **Total return (TWR)** | See §8.1: chain period returns: `(1+r1)(1+r2)...(1+rN) - 1`        |
| **Total return (IRR)** | See §8.1: money-weighted rate (NPV = 0 over all cash flows)        |
| **Distribution**       | `investment_value / total_portfolio_value * 100` per category      |

---

### 8.1 Returns: partial and total (per investment)

When there are deposits and withdrawals, “return” must be defined so that new money does not distort the number. Below is the full model used in the app.

#### Period return (between two snapshots)

**What it measures:** Return on the capital that was already there at the start of the period, excluding the effect of deposits/withdrawals in that period.

- `S_prev` = value at the previous snapshot
- `S_curr` = value at the current snapshot
- `NetCF` = net cash flow in the period (deposits + buy − withdrawals − sell), in the same currency as snapshots

**Formula:**

```
r_period = (S_curr - NetCF) / S_prev - 1
```

**In the UI:** In the investments table, each snapshot cell can show this `r_period` (e.g. +2.3% or −1.1%) relative to the previous snapshot. The first snapshot has no previous cell, so no period return is shown (or N/A).

**Important:** NetCF is summed over the period between the previous snapshot date and the current snapshot date (e.g. one month). All amounts must be in the same currency (convert via exchange_rates at query time if needed).

#### Total return when there are cash flows

Using “final value / initial value − 1” ignores cash flows and is misleading. Two standard total-return definitions are used:

**1. Time-Weighted Return (TWR)**

- **What it measures:** “If I had invested $1 at the start and never added or removed money, what would my return be?” It does not depend on when you deposited or withdrew.
- **How it is calculated:** Chain period returns (multiply growth factors). Do **not** average.

```
TWR_total = (1 + r1) × (1 + r2) × … × (1 + rN) − 1
```

Example: Month 1 +5%, Month 2 −2%, Month 3 +4% → TWR = 1.05 × 0.98 × 1.04 − 1 ≈ +7.02%.

**2. Money-Weighted Return (IRR)**

- **What it measures:** “At what rate did my actual money grow, given when I added and removed it?” It does depend on the timing of cash flows.
- **How it is calculated:** Build the cash-flow series (initial value as outflow, deposits as outflows, withdrawals as inflows, final value as inflow) and solve for the discount rate that makes NPV = 0 (e.g. with `numpy.irr` or XIRR for irregular dates). Result is typically annualised.

#### Summary

| Concept                | Meaning                                      | Formula / method                                   |
| ---------------------- | -------------------------------------------- | -------------------------------------------------- |
| **Period return**      | Return between previous and current snapshot | `r = (S_curr - NetCF) / S_prev - 1`                |
| **Total return (TWR)** | Return “of the market” since inception       | Chain: `(1+r1)(1+r2)...(1+rN) - 1`                 |
| **Total return (IRR)** | Rate at which your capital actually grew     | Solve NPV = 0 over initial, flows, and final value |

#### Other useful metrics per investment

- **Invested capital:** Sum of all deposits − withdrawals (how much you put in).
- **Absolute gain/loss:** Current value − invested capital (in currency).
- **Simple “return” (informational only):** `(current_value / invested_capital) − 1`. Not TWR or IRR; just “how much I have vs how much I put in.”
- **CAGR (annualised):** If the horizon is T years, `(1 + TWR_total)^(1/T) − 1`.
- **Volatility:** Standard deviation of period returns (e.g. monthly) — risk indicator.
- **Drawdown:** Peak-to-trough decline; max drawdown for worst historical drop.
- **Raw change vs previous month:** `(S_curr / S_prev) − 1` without removing flows. Can be shown as “value change” but should be labelled separately from “return.”

---

## 9. Monthly Data Entry Screen

This screen is key to the agility goal. The flow is:

1. The user enters "Data Entry" from the sidebar
2. The current month is pre-selected (editable with a month/year date picker)
3. A table shows all active investments, one per row
4. Each value cell shows the last recorded value as a placeholder — the user only types what changed
5. There is a "Month deposit" column to record any additional capital added, separate from the total value
6. At the bottom of the table there is a separate section to update the month's exchange rates (official, MEP, blue), also with the previous value as placeholder
7. Navigation between cells is done with Tab and Enter, no mouse required
8. A "Save all" button visible at the top executes a batch upsert of all modified values
9. If the save partially fails, the UI shows which rows failed without losing the rest

---

## 10. UX Design Decisions

| Decision                                  | Justification                                                                                                                                                                                                       |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Server-side list/search/filter/pagination | All list views (investments table, snapshots grid scope) call the backend with query params; no client-side filtering of full datasets. Keeps payloads small, scales with data, and keeps a single source of truth. |
| Batch entry in a single screen            | Avoids navigating investment by investment; goal is < 15 min/month                                                                                                                                                  |
| Previous values as placeholders           | User only edits what changed, doesn't re-type everything                                                                                                                                                            |
| Global currency switch                    | One click changes the entire view; state lives in Zustand (client)                                                                                                                                                  |
| Optimistic saving                         | UI responds immediately; on error, a toast is shown and the change is reverted                                                                                                                                      |
| Tab/Enter shortcuts in the table          | Mouse-free navigation on the data entry screen                                                                                                                                                                      |
| Soft delete on investments                | Inactive investments remain part of the portfolio history                                                                                                                                                           |
| Exchange rates on the same entry screen   | User updates everything in one place                                                                                                                                                                                |

---

## 11. UI and navigation (MVP)

Main navigation has **four items** (sidebar or top bar): **Dashboard**, **Investments** (list table), **Snapshots** (grid table), and **Settings**. Below is the detailed UI spec for each.

### 11.1 Dashboard

- **Content:** Metric cards, evolution chart, distribution chart (and compact investments table) as in §8.
- **Scope:** Search/filter by investment, group, or category. When the user selects one (e.g. from a smart search that shows investments, groups, and types), the app navigates to a **filtered dashboard** with the same blocks but data limited to that investment, that group’s investments, or that category. Tapping an investment row in the investments table (see §11.2) can also open this same filtered-dashboard view for that investment; back returns to the table.
- **Currency:** Global switch options come from **Settings** (§11.5): the user configures which currencies to show (e.g. ARS, USD; more can be enabled later) and their order. The switch shows one option per configured currency plus **Original** (each investment in its `base_currency`). Stored values stay in their currency; conversion at display time via `exchange_rates`.

### 11.2 Investments table (first table page)

- **Purpose:** List of investments with metadata and CRUD. **Separate page** from the snapshots grid.
- **Layout:** One table that fits in width on desktop (horizontal scroll only on small screens). No sticky columns needed here.
- **Columns (left to right):**  
  **Id** → **Name** → **Group(s)** (can be multiple; e.g. tags or comma-separated) → **Category** (single type) → **Currency** (base_currency) → … (any other metadata) → **Actions**.
- **Actions column:** Edit (icon) opens a form/modal to edit **only** investment metadata (name, group(s), category, currency, broker, notes, etc.) — not snapshots or transactions. Delete (button or icon) performs soft delete (`is_active = false`).
- **Toolbar above the table (single row):**
  - **Search** (text) to filter by investment name (and optionally group/category labels).
  - **Group filter:** multiselect; **union** of selected groups (investments that belong to _any_ selected group); if none selected, show all.
  - **Category filter:** single select (one category type); if “All” or empty, show all.
  - **CTA “Add investment”** at the end of the row (opens create-investment flow; modal or dedicated route).
- **Row click:** Clicking anywhere on a row (except the Actions cells) navigates to the **filtered dashboard** for that investment (same view as dashboard filtered by that investment). Back button returns to this investments table.

### 11.3 Snapshots table (second table page)

- **Purpose:** Grid of snapshot values by investment (rows) and month (columns), with period return and transaction indicators. **Separate page** from the investments list.
- **Layout:** **Scrollable both horizontally and vertically** (many months). Consider a **sticky right column** for “Actions” so that when the user scrolls far right to see recent months, the “Add snapshot” control remains visible.
- **Cell content (per snapshot):**
  - Main: snapshot **value** (in the chosen display currency).
  - To the right of the value: small **period-return indicator** — up arrow (green) or down arrow (red) + percentage (see §8.1). First snapshot in the row has no period return (N/A).
  - Indicator if there was a **transaction** (deposit/withdrawal) in that period (e.g. small icon or badge) so the user sees “this month had an inflow/outflow”.
- **Adding snapshots/transactions:**
  - **Preferred:** A fixed **Actions** column on the right (sticky when scrolling horizontally) with an “Add snapshot” control (e.g. per row or one “Add month” that adds a new column). When adding or editing a snapshot, the flow includes **transactions for that period** (create/edit snapshot and optional transactions in the same flow).
  - **Alternative:** A final “empty” column for “next month” with a “+” cell to add the next snapshot; behaviour can match the same create-snapshot + transactions flow. Either approach is acceptable; the sticky Actions column is recommended so it’s always visible.
- **Editing snapshots:** **Tap/click the cell** to edit the snapshot (and associated transactions for that period) inline or in a small inline form/modal, instead of a separate edit icon per cell to reduce clutter.
- **Filters:** Same search and filters as the investments table (search by name, filter by group multiselect, filter by category) so the user can narrow the grid to a subset of investments even though the columns are months. Group/category don’t need to appear as columns in this grid. Filter changes trigger a backend call; rows (investments) and snapshot data are returned by the API (server-side; see §10).

### 11.4 Currency display (global)

- **Control:** A switch or dropdown built from **Settings**: one option per currency enabled in Settings (e.g. ARS, USD; see §11.5) plus **Original** (each investment in its `base_currency`). Current selection can live in Zustand and be passed to dashboard and both tables. If the user has not configured Settings yet, fallback to a default (e.g. ARS, USD, Original).

### 11.5 Settings page (MVP)

- **Purpose:** Setup and preferences. In the MVP this page is **explicitly part of the scope** and is the single place for app-level configuration; it has room to grow in later versions (more options, themes, defaults).
- **Currency setup (MVP):** A form where the user defines which **currencies** appear in the global switch and in what order (e.g. checkboxes or multi-select for “Display currencies”, plus optional “Default currency” for first load). Stored in `user_settings` (e.g. `display_currencies`, `default_currency`). Backend exposes `GET /settings` and `PUT /settings`. With 2 currencies (ARS, USD) the form is minimal; more currencies can be enabled when the enum or data model is extended (e.g. “varios dólares”).
- **Future expansion:** Same page can later host: default dashboard period, date format, theme, notification preferences, etc., without adding new nav items.

### 11.6 Deferred to later

- **Full “configure investment” page:** A dedicated page (not just a modal) to create an investment and optionally add snapshots and transactions manually. **Deferred** to a later version.
- **CSV import:** Import of snapshots/transactions from CSV. **Deferred** to a later version.

---

## 12. Preparation for Future Phases

### Phase 2 — Income and Expenses

Tables to be added:

```sql
income_entries     (id, user_id, date, amount, currency, category_id, notes)
expense_entries    (id, user_id, date, amount, currency, category_id, notes)
income_categories  (id, name, type)   -- salary, rent, dividends, etc.
expense_categories (id, name, type)   -- food, transport, entertainment, etc.
```

The currency model and `exchange_rates` table already cover this phase without changes.

### Phase 3 — Structured Expenses

```sql
subscriptions  (id, user_id, name, amount, currency, billing_cycle, is_active, next_billing_date)
installments   (id, user_id, name, total_amount, installments_count, current_installment, start_date)
```

### Phase 4 — Automation

- **Cocos Capital**: has a publicly documented API
- **Mercado Pago**: official API available
- **Home banking**: scraping with `playwright` (Python) or unofficial APIs
- The flow would be: scraping generates automatic `transactions` and `investment_snapshots` with a `source: "auto"` flag so the user can review before confirming

---

## 13. Environment Variables

### Frontend (`apps/web/.env.local`)

```
NEXTAUTH_SECRET=
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend (`apps/api/.env`)

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/renly
JWT_SECRET=           # same secret as NEXTAUTH_SECRET
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080  # 7 days
BLUELYTICS_API_URL=https://api.bluelytics.com.ar/v2
```

---

## 14. Development Commands

```bash
# Install dependencies (from root)
pnpm install

# Start everything (frontend + backend + DB)
docker-compose up -d postgres
turbo dev

# Frontend only
cd apps/web && pnpm dev

# Backend only
cd apps/api && uvicorn app.main:app --reload

# Tests
turbo test
```

---

## 15. MVP Implementation Checklist

### Infrastructure

- [x] Create GitHub repo
- [x] Initialize monorepo with Turborepo and pnpm workspaces
- [x] Configure `docker-compose.yml` with local PostgreSQL
- [ ] Set up Supabase (create project, get connection string)
- [ ] Set up Railway (create project, connect repo)
- [ ] Set up Vercel (connect repo, environment variables)

### Backend

- [x] FastAPI scaffold with folder structure
- [x] Configure SQLModel + Alembic
- [x] Base tables via `database/01_create_tables.sql` (applied with `pnpm db:init`)
- [x] SQLModel models: `User`, `Investment`, `InvestmentSnapshot`, `Transaction`, `ExchangeRate`, `InvestmentTarget`, `InvestmentGroup`, `InvestmentGroupMember`, `UserSettings`
- [x] Groups: `investment_groups`, `investment_group_members` in `01_create_tables.sql`; groups CRUD + membership API (see §7)
- [x] Settings: `user_settings` in `01_create_tables.sql`; GET/PUT /settings for display_currencies, default_currency (§7)
- [x] JWT authentication: register, login, logout, me; token validation in middleware
- [x] Investment CRUD (list, get, create, update, soft delete)
- [x] Snapshot endpoints (list, upsert by date); transaction endpoints (list, get, create, update, delete)
- [ ] Metrics service (period return, TWR, IRR, portfolio aggregates; see §8.1)
- [ ] Exchange rate update job (bluelytics)
- [ ] Unit tests for metrics services

### Frontend

- [x] Next.js scaffold with App Router and TypeScript
- [x] Tailwind + shared UI package (`packages/ui`: button, card, input, table, dialog, etc.)
- [x] NextAuth with credentials provider (login, signup)
- [x] Protected layout (redirect to login when unauthenticated)
- [x] Dashboard route (placeholder: welcome + user name)
- [x] Sidebar/topbar: Dashboard, Investments (table), Snapshots (table), Settings
- [ ] Dashboard (§11.1): metric cards, evolution chart, distribution; search/filter by investment, group, category; drill-down to filtered dashboard view
- [ ] Global currency: switch/dropdown built from Settings (display_currencies + Original); Zustand for current selection
- [ ] Investments table page (§11.2): columns Id, Name, Group(s), Category, Currency, Actions (edit metadata, soft delete); toolbar with search, group multiselect filter, category filter, “Add investment” CTA; row click → filtered dashboard for that investment
- [ ] Snapshots table page (§11.3): rows = investments, columns = months; cell = value + period-return indicator (↑ green / ↓ red + %) + transaction indicator; sticky Actions column with “Add snapshot”; tap cell to edit snapshot + transactions; optional search/filters by name, group, category
- [x] Settings page (§11.5): form to configure primary and secondary currencies; GET/PUT settings API; uses `CurrencyCombobox` with flag emoji, search, and scoring; placeholder for future options
- [ ] (Future) Full “configure investment” page and CSV import

---

## 16. Current implementation status (as of March 2026)

**Repo name:** Renly. Monorepo: `apps/web` (Next.js), `apps/api` (FastAPI), `packages/ui`, `packages/eslint-config`, `packages/typescript-config`. DB schema: `apps/api/database/01_create_tables.sql`.

**Backend (implemented):**

- Auth: `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`. JWT in header; bcrypt passwords.
- Investments: full CRUD; snapshots list + upsert by (investment_id, date); transactions list, get, create, update, delete.
- Groups: `GET/POST /groups`, `GET/PUT/DELETE /groups/{id}`, `PUT /groups/{id}/investments`; CRUD + membership (investment_ids).
- Settings: `GET /settings`, `PUT /settings` (display_currencies, default_currency; partial update, defaults when no row).
- Not yet: metrics router, exchange-rates router, scheduled jobs.

**Frontend (implemented):**

- Auth: login and signup pages; NextAuth credentials provider; session with access token forwarded to API.
- Protected area: layout that redirects to login if no session; dashboard page (title + welcome message only).
- Sidebar: shadcn/ui `Sidebar` component with nav items (Dashboard, Investments, Snapshots, Settings) and a logout button in the footer. Desktop sidebar is always expanded (collapsing disabled). Mobile renders a Sheet overlay. Active item highlighted in blue. Translations in `apps/web/translations/{en,es}.json` under the `sidebar` key.
- Settings page implemented: primary and secondary currency selection via `CurrencyCombobox` (flag emoji, ranked search, ISO 3166-1 allowlist). Stored via `PUT /settings`.
- No investments list/detail, no data-entry, no currency switch.

**Development:** From root: `pnpm install`, `pnpm build`, `pnpm db:init` (first-time DB), `pnpm dev`. API runs on port 8000, web on 3000. See root `README.md` and `apps/api/README.md` for details.

---

\_Version 1.5 — March 2026. For the Spanish version, see `arquitectura-es.md`.
