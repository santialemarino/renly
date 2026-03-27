# Scheduled jobs for background tasks (exchange rates, asset prices).

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import AsyncSessionLocal
from app.services import asset_price_service, cedear_ratio_service, exchange_rate_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


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
        hours=6,
        id="update_exchange_rates",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    # Asset prices: run weekly (every Sunday at 20:00 UTC).
    scheduler.add_job(
        _update_asset_prices,
        "cron",
        day_of_week="sun",
        hour=20,
        id="update_asset_prices",
        replace_existing=True,
    )

    # CEDEAR ratios: run monthly (1st of each month at 12:00 UTC) + on startup.
    scheduler.add_job(
        _update_cedear_ratios,
        "cron",
        day=1,
        hour=12,
        id="update_cedear_ratios",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    scheduler.start()
    logger.info(
        "Scheduler started (exchange rates: now + every 6h, "
        "asset prices: weekly Sun 20:00 UTC, "
        "CEDEAR ratios: now + monthly 1st 12:00 UTC)."
    )


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")
