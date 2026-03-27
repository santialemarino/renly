# Scheduled jobs for background tasks (exchange rates, asset prices, auto-snapshots, CEDEAR ratios).

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import AsyncSessionLocal
from app.services import asset_price_service, auto_snapshot_service, cedear_ratio_service, exchange_rate_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Schedule configuration.
EXCHANGE_RATES_INTERVAL_HOURS = 6
ASSET_PRICES_HOUR_UTC = 22
AUTO_SNAPSHOTS_HOUR_UTC = 23
CEDEAR_RATIOS_DAY_OF_MONTH = 1
CEDEAR_RATIOS_HOUR_UTC = 0


# Fetches latest exchange rates from all sources (DolarApi + Frankfurter) and stores them.
async def _update_exchange_rates() -> None:
    try:
        async with AsyncSessionLocal() as session:
            await exchange_rate_service.fetch_and_store_latest(session)
    except Exception:
        logger.exception("Scheduled exchange rate update failed.")


# Fetches latest asset prices for all ticker-linked investments.
async def _update_asset_prices() -> None:
    try:
        async with AsyncSessionLocal() as session:
            count = await asset_price_service.refresh_all_prices(session)
            logger.info("Scheduled asset price update: %d prices stored.", count)
    except Exception:
        logger.exception("Scheduled asset price update failed.")


# Generates auto-snapshots for ticker-linked investments using latest prices.
async def _generate_auto_snapshots() -> None:
    try:
        async with AsyncSessionLocal() as session:
            count = await auto_snapshot_service.generate_auto_snapshots(session)
            logger.info("Scheduled auto-snapshots: %d snapshots created.", count)
    except Exception:
        logger.exception("Scheduled auto-snapshot generation failed.")


# Fetches CEDEAR ratios from Banco Comafi.
async def _update_cedear_ratios() -> None:
    try:
        async with AsyncSessionLocal() as session:
            count = await cedear_ratio_service.fetch_and_store_ratios(session)
            logger.info("Scheduled CEDEAR ratio update: %d ratios stored.", count)
    except Exception:
        logger.exception("Scheduled CEDEAR ratio update failed.")


def start_scheduler() -> None:
    from datetime import datetime

    # Exchange rates: run immediately on startup, then every 6 hours.
    scheduler.add_job(
        _update_exchange_rates,
        "interval",
        hours=EXCHANGE_RATES_INTERVAL_HOURS,
        id="update_exchange_rates",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    # Asset prices: run daily at 22:00 UTC (after US + Argentine market close).
    scheduler.add_job(
        _update_asset_prices,
        "cron",
        hour=ASSET_PRICES_HOUR_UTC,
        id="update_asset_prices",
        replace_existing=True,
    )

    # Auto-snapshots: run on the last day of each month at 23:00 UTC (after price fetch).
    scheduler.add_job(
        _generate_auto_snapshots,
        "cron",
        day="last",
        hour=AUTO_SNAPSHOTS_HOUR_UTC,
        id="generate_auto_snapshots",
        replace_existing=True,
    )

    # CEDEAR ratios: run monthly (1st of each month at 00:00 UTC) + on startup.
    scheduler.add_job(
        _update_cedear_ratios,
        "cron",
        day=CEDEAR_RATIOS_DAY_OF_MONTH,
        hour=CEDEAR_RATIOS_HOUR_UTC,
        id="update_cedear_ratios",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    scheduler.start()
    logger.info(
        "Scheduler started (exchange rates: now + every %dh, "
        "asset prices: daily %02d:00 UTC, "
        "auto-snapshots: last day %02d:00 UTC, "
        "CEDEAR ratios: now + monthly %dth %02d:00 UTC).",
        EXCHANGE_RATES_INTERVAL_HOURS,
        ASSET_PRICES_HOUR_UTC,
        AUTO_SNAPSHOTS_HOUR_UTC,
        CEDEAR_RATIOS_DAY_OF_MONTH,
        CEDEAR_RATIOS_HOUR_UTC,
    )


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")
