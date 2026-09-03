# Scheduler

APScheduler-based background job system for periodic data fetching and auto-snapshot generation.

**File:** `apps/api/app/scheduler.py`

## Setup

The scheduler uses `APScheduler.AsyncIOScheduler` and integrates with FastAPI's lifespan. `start_scheduler()` is called on app startup; `stop_scheduler()` on shutdown. It is pinned to UTC (`AsyncIOScheduler(timezone="UTC")`), so every cron hour below (the `*_HOUR_UTC` constants) fires at that UTC hour regardless of the host's local timezone — matching the startup catch-up's UTC reasoning.

Each job wrapper creates its own `AdminSessionLocal()` session (not tied to a request) and catches all exceptions at the top level — a failing job logs the error and does not crash the application. Background jobs run with no user context, so they use the **privileged** session (`DATABASE_ADMIN_URL`, the table owner) which bypasses Row-Level Security (SEC-15) — a single job legitimately spans every user's rows.

## Configuration constants

In `apps/api/app/scheduler.py`:

```python
EXCHANGE_RATES_INTERVAL_HOURS = 6
ASSET_PRICES_HOUR_UTC = 22
AUTO_SNAPSHOTS_HOUR_UTC = 23
CEDEAR_RATIOS_DAY_OF_MONTH = 1
CEDEAR_RATIOS_HOUR_UTC = 0
MISFIRE_GRACE_SECONDS = 6 * 3600
AUTO_SNAPSHOTS_CATCHUP_DAYS = 3
```

### Misfire policy

Every job is registered with `misfire_grace_time=MISFIRE_GRACE_SECONDS` (6h) and `coalesce=True`. The job store is in-memory, so APScheduler's default 1s grace would silently skip any tick the event loop couldn't serve on time; 6h of grace lets a late tick still fire, and `coalesce=True` collapses multiple missed runs into a single one (never a burst). Every job here is idempotent / back-filling, so a late run is safe. Grace cannot help across a **restart**, though — the in-memory store loses all schedule state, so a tick missed while the process was down is unrecoverable by grace alone. The month-end auto-snapshot therefore has a dedicated startup catch-up (job 7).

Two jobs fire at each user's own LOCAL hour rather than at a UTC one, so their hour constant lives with the service that owns the per-user filter — the scheduler tick itself is hourly and has no UTC-hour constant for them. In `apps/api/app/services/auto_expense_service.py` and `apps/api/app/services/pot_reminder_service.py`:

```python
AUTO_EXPENSES_HOUR_LOCAL = 1
SNAPSHOT_REMINDER_HOUR_LOCAL = 9
```

The reminder's hour is a waking one and the auto-expense job's is not, deliberately: one is a message asking somebody to do something, the other a silent background write nobody reads.

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

Runs after US and Argentine market close. Individual ticker failures are skipped (not the entire job). `refresh_all_prices` is the **system-wide** refresh and is reserved for this scheduled job; the on-demand `POST /asset-prices/refresh` endpoint instead calls `refresh_user_prices(session, user_id)`, which fetches only the calling user's tickers.

### 3. Auto-snapshots

| Property         | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (last day of month at 23:00 UTC)                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Service call** | `auto_snapshot_service.generate_auto_snapshots(session)`                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **What it does** | For each ticker-linked investment: latest price x last known quantity = new snapshot with `source: 'auto'`. Skips if a snapshot already exists for today or no price data is available. Also skips an investment whose latest snapshot has no usable quantity (None or ≤ 0 — otherwise it would record the price of one share as the whole position; logged at debug) or whose latest price is quoted in a different currency than the investment's base (logged at warning; no conversion is attempted). |

Runs 1 hour after the asset prices job to ensure fresh prices are available.

### 4. Auto-expenses

| Property         | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (hourly, every UTC hour at HH:00)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **Service call** | `auto_expense_service.generate_auto_expenses(session)`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **What it does** | Each UTC tick the service first prunes candidate plans in SQL — `subscription_repository.list_active_due` / `installment_repository.list_active_due` return only active plans due at or before `utc_today + 1 day` (the +1 covers every user's local today up to UTC+14), so the tick never loads the whole active set into Python. It then loads every user's timezone in one batch, filters to users whose **local-time-now hour equals `AUTO_EXPENSES_HOUR_LOCAL`** (= 1), and retroactively emits `expense_entries`: every active subscription whose `next_billing_date <= today_for_user` and every active installment whose next cuota is at or before `today_for_user`. The per-user local-date comparison is the correctness layer; the SQL bound only prunes. Each generated entry carries the source plan's FK (`subscription_id` or `installment_id`) and `source` accordingly, plus the plan's **default funding account** when it still qualifies, so an auto-generated charge decrements the balance it really came out of. |

The hourly tick + per-user-local-hour filter means each user's auto-expenses fire at their own local 01:00. A user in `America/Argentina/Buenos_Aires` (UTC-3) processes at 04:00 UTC; a user in `America/New_York` EST processes at 06:00 UTC; a user in UTC processes at 01:00 UTC. `today_for_user = datetime.now(ZoneInfo(user.tz)).date()` so the `next_billing_date <= today` comparison lands on the user's local calendar — a subscription with `next_billing_date = 2026-05-25` only fires once the user's local-now has actually crossed into 2026-05-25.

User timezone comes from `user_settings.settings.timezone` (IANA name; auto-detected from the browser, manual override available on the `/localization` page). Users with no timezone set fall back to UTC (day-zero behaviour for un-filled users matches the pre-Step-G design exactly). Invalid IANA names are caught by the settings router on write; if a stale invalid value ever reaches the scheduler at runtime it logs a warning and falls back to UTC.

Idempotent on re-runs via **cycle-proximity dedup**: every expense already linked to a plan claims the cycle (or installment cuota) its own date binds to under the same closest-cycle matching the manual-entry advance uses, and the back-fill loop skips any cycle already claimed. Because an off-date payment (e.g. an expense dated Jun 28 that paid the Jun 30 cycle) claims the cycle it actually belongs to — not just an exact-date match — a pre-paid cycle is never double-emitted. Exact-date rows claim their own cycle, so this subsumes the old exact-date pre-check; the partial unique indexes on `(subscription_id, date)` / `(installment_id, date)` remain as a last-resort backstop. Cursor advances persist even on emission-free ticks: when dedup suppresses every insert for a plan, `next_billing_date` / `current_installment` still moves past the paid cycle and the run commits so the cursor catches up. Once an installment plan reaches `current_installment > installments_count`, `is_active` flips to `false` automatically.

**Default funding account.** A plan may name the cash/bank account it is paid from, and each emitted charge is linked to it
(`expense_entries.account_id`), which is what keeps the account's derived balance honest without the user touching anything.
All of a tick's referenced accounts load in **one** query (`account_repository.get_by_ids_across_users` — deliberately
unscoped, since a tick spans many users), and each row is then re-checked before the link is written: the account must belong
to the plan's owner (SEC-4) and share its currency, because the balance union sums linked rows without conversion. A default
that no longer qualifies — its account's currency was changed while nothing but this default referenced it, so nothing locked
it — is **skipped, not fatal**: the charge still lands, merely unattributed, exactly as it did before defaults existed, and
reconciliation remains the backstop. A card-paid plan never carries one (its cash leg lands at the card settlement).

### 5. CEDEAR ratios

| Property         | Value                                                                                                                                                            |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `cron` (1st of month at 00:00 UTC)                                                                                                                               |
| **Also runs**    | Immediately on startup (`next_run_time=datetime.now()`)                                                                                                          |
| **Service call** | `cedear_ratio_service.fetch_and_store_ratios(session)`                                                                                                           |
| **What it does** | Fetches Banco Comafi Excel and BYMA PDF in parallel, picks the most complete source (newer date → more entries → Comafi preferred), upserts into `cedear_ratios` |

### 6. Pot valuation reminders

| Property         | Value                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Trigger**      | `cron` (hourly, minute 0)                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Service call** | `pot_reminder_service.send_due_reminders(session)`                                                                                                                                                                                                                                                                                                                                                                                   |
| **What it does** | Notifies a shared pot's WRITERS when its valuation has fallen behind the cadence the group agreed on (§9's third job for `snapshot_cadence`). Hourly because the filter is per user: only members whose local time is now `SNAPSHOT_REMINDER_HOUR_LOCAL` (9) are considered, so each person is reached in their own morning. Writers rather than every viewer, because only a member with `can_write` can snapshot a shared holding. |
| **Idempotence**  | Through the notification's `dedupe_key` (`pot:<id>:<cadence period>`) and the partial unique index behind it — not through state of its own. The job may run any number of times and reach different people on different ticks, and each person is still told at most once per period. A pot still overdue when the next period opens produces a new key, so it nudges again.                                                        |
| **Cost**         | Prunes before it measures: the roster, permissions and timezones load once (three queries), and only pots with somebody actually due are valued at all. Freshness is read with `pot_service.get_freshness`, which needs no NAV and no rate lookup — so the job never pays for the expensive balance union.                                                                                                                           |

### 7. Auto-snapshot startup catch-up

| Field            | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trigger**      | `date` (one-shot, `run_date=datetime.now(UTC)` at startup)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Service call** | `auto_snapshot_service.run_startup_catchup(session, catchup_days=AUTO_SNAPSHOTS_CATCHUP_DAYS, snapshots_hour_utc=AUTO_SNAPSHOTS_HOUR_UTC)`                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **What it does** | Runs the month-end auto-snapshot once if a restart spanned the month-end tick. Fires `generate_auto_snapshots` only when now is within `AUTO_SNAPSHOTS_CATCHUP_DAYS` (3) after the most recent month-end fire time (month-end date at `AUTO_SNAPSHOTS_HOUR_UTC`) **and** no `source='auto'` snapshot exists dated on or after that month-end. Snapshots created here are dated today — a few days late beats a missing month. Necessary because the in-memory job store loses schedule state on restart, so `misfire_grace_time` cannot recover a tick missed while the process was down. |

## Error handling

Every job wrapper follows the same pattern:

```python
async def _job_name() -> None:
    try:
        async with AdminSessionLocal() as session:
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
5. Always set `misfire_grace_time=MISFIRE_GRACE_SECONDS, coalesce=True` (the in-memory store makes a stricter grace unsafe; jobs must be idempotent so a coalesced late run is fine).
6. For jobs that should run on startup, pass `next_run_time=datetime.now()`.
7. Add a configuration constant at the top of the file for any schedule parameters.
