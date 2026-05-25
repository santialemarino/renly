# Scheduler

APScheduler-based background job system for periodic data fetching and auto-snapshot generation.

**File:** `apps/api/app/scheduler.py`

## Setup

The scheduler uses `APScheduler.AsyncIOScheduler` and integrates with FastAPI's lifespan. `start_scheduler()` is called on app startup; `stop_scheduler()` on shutdown.

Each job wrapper creates its own `AsyncSessionLocal()` session (not tied to a request) and catches all exceptions at the top level — a failing job logs the error and does not crash the application.

## Configuration constants

```python
EXCHANGE_RATES_INTERVAL_HOURS = 6
ASSET_PRICES_HOUR_UTC = 22
AUTO_SNAPSHOTS_HOUR_UTC = 23
AUTO_EXPENSES_HOUR_LOCAL = 1
CEDEAR_RATIOS_DAY_OF_MONTH = 1
CEDEAR_RATIOS_HOUR_UTC = 0
```

## Jobs

### 1. Exchange rates

| Property         | Value                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| **Trigger**      | `interval` (every 6 hours)                                                                             |
| **Also runs**    | Immediately on startup (`next_run_time=datetime.now()`)                                                |
| **Service call** | `exchange_rate_service.fetch_and_store_latest(session)`                                                |
| **What it does** | Fetches rates from all registered providers (DolarApi + Frankfurter) and upserts into `exchange_rates` |

### 2. Asset prices

| Property         | Value                                                                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (daily at 22:00 UTC)                                                                                                                               |
| **Service call** | `asset_price_service.refresh_all_prices(session)`                                                                                                         |
| **What it does** | Iterates all ticker-linked investments, calls the appropriate price provider for each, stores results in `asset_prices`. Logs the count of prices stored. |

Runs after US and Argentine market close. Individual ticker failures are skipped (not the entire job).

### 3. Auto-snapshots

| Property         | Value                                                                                                                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (last day of month at 23:00 UTC)                                                                                                                                                 |
| **Service call** | `auto_snapshot_service.generate_auto_snapshots(session)`                                                                                                                                |
| **What it does** | For each ticker-linked investment: latest price x last known quantity = new snapshot with `source: 'auto'`. Skips if a snapshot already exists for today or no price data is available. |

Runs 1 hour after the asset prices job to ensure fresh prices are available.

### 4. Auto-expenses

| Property         | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (hourly, every UTC hour at HH:00)                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Service call** | `auto_expense_service.generate_auto_expenses(session)`                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **What it does** | Each UTC tick the service loads every user's timezone in one batch, filters to users whose **local-time-now hour equals `AUTO_EXPENSES_HOUR_LOCAL`** (= 1), then retroactively emits `expense_entries` for those users: every active subscription whose `next_billing_date <= today_for_user` and every active installment whose next cuota is at or before `today_for_user`. Each generated entry carries the source plan's FK (`subscription_id` or `installment_id`) and `source` accordingly. |

The hourly tick + per-user-local-hour filter means each user's auto-expenses fire at their own local 01:00. A user in `America/Argentina/Buenos_Aires` (UTC-3) processes at 04:00 UTC; a user in `America/New_York` EST processes at 06:00 UTC; a user in UTC processes at 01:00 UTC. `today_for_user = datetime.now(ZoneInfo(user.tz)).date()` so the `next_billing_date <= today` comparison lands on the user's local calendar — a subscription with `next_billing_date = 2026-05-25` only fires once the user's local-now has actually crossed into 2026-05-25.

User timezone comes from `user_settings.settings.timezone` (IANA name; auto-detected from the browser, manual override available on the `/localization` page). Users with no timezone set fall back to UTC (day-zero behaviour for un-filled users matches the pre-Step-G design exactly). Invalid IANA names are caught by the settings router on write; if a stale invalid value ever reaches the scheduler at runtime it logs a warning and falls back to UTC.

Idempotent on re-runs: partial unique indexes on `(subscription_id, date)` / `(installment_id, date)` plus a pre-check skip in the service prevent double-insertion. Once an installment plan reaches `current_installment > installments_count`, `is_active` flips to `false` automatically.

### 5. CEDEAR ratios

| Property         | Value                                                                                                                                                            |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (1st of month at 00:00 UTC)                                                                                                                               |
| **Also runs**    | Immediately on startup (`next_run_time=datetime.now()`)                                                                                                          |
| **Service call** | `cedear_ratio_service.fetch_and_store_ratios(session)`                                                                                                           |
| **What it does** | Fetches Banco Comafi Excel and BYMA PDF in parallel, picks the most complete source (newer date → more entries → Comafi preferred), upserts into `cedear_ratios` |

## Error handling

Every job wrapper follows the same pattern:

```python
async def _job_name() -> None:
    try:
        async with AsyncSessionLocal() as session:
            await service.method(session)
    except Exception:
        logger.exception("Scheduled <job> failed.")
```

Failures are logged but never propagated — the scheduler continues running other jobs.

## Adding a new job

1. Create an async wrapper function that opens a session and calls the service method.
2. Wrap the body in `try/except Exception` with `logger.exception()`.
3. Add `scheduler.add_job(...)` in `start_scheduler()` with the appropriate trigger (`interval`, `cron`, or `date`).
4. Use `replace_existing=True` and assign a unique `id`.
5. For jobs that should run on startup, pass `next_run_time=datetime.now()`.
6. Add a configuration constant at the top of the file for any schedule parameters.
