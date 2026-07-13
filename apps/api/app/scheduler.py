# Scheduled jobs for background tasks (exchange rates, asset prices, auto-snapshots, CEDEAR ratios).

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Background jobs run with no user context, so they use the privileged (RLS-bypassing) session.
from app.db import AdminSessionLocal
from app.services import (
    asset_price_service,
    auto_expense_service,
    auto_snapshot_service,
    cedear_ratio_service,
    exchange_rate_service,
)

logger = logging.getLogger(__name__)

# Pinned to UTC so the cron hours below (all named *_HOUR_UTC) fire at those UTC hours regardless
# of the host's local timezone, matching the startup catch-up's UTC reasoning. (A bare
# datetime.timezone is rejected by APScheduler 3.x — it wants a named/pytz zone, hence the string.)
scheduler = AsyncIOScheduler(timezone="UTC")

# Schedule configuration.
EXCHANGE_RATES_INTERVAL_HOURS = 6
ASSET_PRICES_HOUR_UTC = 22
AUTO_SNAPSHOTS_HOUR_UTC = 23
CEDEAR_RATIOS_DAY_OF_MONTH = 1
CEDEAR_RATIOS_HOUR_UTC = 0

# Misfire policy: with the in-memory job store, APScheduler's default 1s grace silently skips any
# tick the loop couldn't serve on time. Six hours of grace + coalesce=True means a late tick fires
# exactly once (never a burst) — every job here is idempotent/back-filling, so a late run is safe.
MISFIRE_GRACE_SECONDS = 6 * 3600
# Days after a month-end within which the startup catch-up will still run a missed auto-snapshot.
AUTO_SNAPSHOTS_CATCHUP_DAYS = 3


# Fetches latest exchange rates from all sources (DolarApi + Frankfurter) and stores them.
async def _update_exchange_rates() -> None:
    try:
        async with AdminSessionLocal() as session:
            await exchange_rate_service.fetch_and_store_latest(session)
    except Exception:
        logger.exception("Scheduled exchange rate update failed.")


# Fetches latest asset prices for all ticker-linked investments.
async def _update_asset_prices() -> None:
    try:
        async with AdminSessionLocal() as session:
            count = await asset_price_service.refresh_all_prices(session)
            logger.info("Scheduled asset price update: %d prices stored.", count)
    except Exception:
        logger.exception("Scheduled asset price update failed.")


# Generates auto-snapshots for ticker-linked investments using latest prices.
async def _generate_auto_snapshots() -> None:
    try:
        async with AdminSessionLocal() as session:
            count = await auto_snapshot_service.generate_auto_snapshots(session)
            logger.info("Scheduled auto-snapshots: %d snapshots created.", count)
    except Exception:
        logger.exception("Scheduled auto-snapshot generation failed.")


# Generates expense_entries from active subscriptions and installment plans.
# Loops retroactively per record so missed cycles back-fill on the next tick.
async def _generate_auto_expenses() -> None:
    try:
        async with AdminSessionLocal() as session:
            count = await auto_expense_service.generate_auto_expenses(session)
            logger.info("Scheduled auto-expenses: %d entries created.", count)
    except Exception:
        logger.exception("Scheduled auto-expense generation failed.")


# Fetches CEDEAR ratios from Banco Comafi.
async def _update_cedear_ratios() -> None:
    try:
        async with AdminSessionLocal() as session:
            count = await cedear_ratio_service.fetch_and_store_ratios(session)
            logger.info("Scheduled CEDEAR ratio update: %d ratios stored.", count)
    except Exception:
        logger.exception("Scheduled CEDEAR ratio update failed.")


# Startup catch-up for the month-end auto-snapshot job. The in-memory job store loses all schedule
# state on restart, so a restart spanning the month-end tick would silently skip a whole month of
# auto-snapshots — misfire_grace_time cannot help across restarts. The window/dedup logic lives in
# the service; this wrapper only owns the session + error isolation.
async def _auto_snapshots_startup_catchup() -> None:
    try:
        async with AdminSessionLocal() as session:
            ran = await auto_snapshot_service.run_startup_catchup(
                session,
                catchup_days=AUTO_SNAPSHOTS_CATCHUP_DAYS,
                snapshots_hour_utc=AUTO_SNAPSHOTS_HOUR_UTC,
            )
            if ran:
                logger.info("Auto-snapshot startup catch-up ran (missed month-end tick detected).")
    except Exception:
        logger.exception("Auto-snapshot startup catch-up failed.")


# Registers all background jobs and starts the scheduler. Called from the app lifespan on startup.
def start_scheduler() -> None:
    # Exchange rates: run immediately on startup, then every 6 hours.
    scheduler.add_job(
        _update_exchange_rates,
        "interval",
        hours=EXCHANGE_RATES_INTERVAL_HOURS,
        id="update_exchange_rates",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
        next_run_time=datetime.now(UTC),
    )

    # Asset prices: run daily at 22:00 UTC (after US + Argentine market close).
    scheduler.add_job(
        _update_asset_prices,
        "cron",
        hour=ASSET_PRICES_HOUR_UTC,
        id="update_asset_prices",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
    )

    # Auto-snapshots: run on the last day of each month at 23:00 UTC (after price fetch).
    scheduler.add_job(
        _generate_auto_snapshots,
        "cron",
        day="last",
        hour=AUTO_SNAPSHOTS_HOUR_UTC,
        id="generate_auto_snapshots",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
    )

    # Auto-expenses: run hourly. The service filters users whose local-time-now hour
    # equals AUTO_EXPENSES_HOUR_LOCAL (= 1) so each user's charges fire at their own
    # local 01:00 instead of a single global UTC tick.
    scheduler.add_job(
        _generate_auto_expenses,
        "cron",
        minute=0,
        id="generate_auto_expenses",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
    )

    # CEDEAR ratios: run monthly (1st of each month at 00:00 UTC) + on startup.
    scheduler.add_job(
        _update_cedear_ratios,
        "cron",
        day=CEDEAR_RATIOS_DAY_OF_MONTH,
        hour=CEDEAR_RATIOS_HOUR_UTC,
        id="update_cedear_ratios",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
        next_run_time=datetime.now(UTC),
    )

    # One-shot startup check for a month-end auto-snapshot missed across a restart.
    scheduler.add_job(
        _auto_snapshots_startup_catchup,
        "date",
        run_date=datetime.now(UTC),
        id="auto_snapshots_startup_catchup",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started (exchange rates: now + every %dh, "
        "asset prices: daily %02d:00 UTC, "
        "auto-snapshots: last day %02d:00 UTC, "
        "auto-expenses: hourly (per-user local 01:00), "
        "CEDEAR ratios: now + monthly %dth %02d:00 UTC).",
        EXCHANGE_RATES_INTERVAL_HOURS,
        ASSET_PRICES_HOUR_UTC,
        AUTO_SNAPSHOTS_HOUR_UTC,
        CEDEAR_RATIOS_DAY_OF_MONTH,
        CEDEAR_RATIOS_HOUR_UTC,
    )


# Stops the scheduler without waiting for running jobs. Called from the app lifespan on shutdown.
def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")
