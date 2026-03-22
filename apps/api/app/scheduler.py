# Scheduled jobs for background tasks (e.g. exchange rate updates).

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import AsyncSessionLocal
from app.services import exchange_rate_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# Fetches latest exchange rates from DolarApi and stores them.
async def _update_exchange_rates() -> None:
    try:
        async with AsyncSessionLocal() as session:
            await exchange_rate_service.fetch_and_store_latest(session)
    except Exception:
        logger.exception("Scheduled exchange rate update failed.")


def start_scheduler() -> None:
    from datetime import datetime

    # Run immediately on startup, then every 6 hours.
    scheduler.add_job(
        _update_exchange_rates,
        "interval",
        hours=6,
        id="update_exchange_rates",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info("Scheduler started (exchange rate update: now + every 6 hours).")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")
