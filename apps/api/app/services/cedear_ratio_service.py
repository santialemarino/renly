# Business logic for CEDEAR ratios: fetching from Comafi and storing in the DB.

import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cedear_ratio import CedearRatio
from app.repositories.cedear_ratio_repository import cedear_ratio_repository
from app.services import price_providers
from app.services.price_providers import COMAFI_SOURCE

logger = logging.getLogger(__name__)


# Returns the current ratio for a CEDEAR ticker. Returns None if not found.
async def get_ratio(session: AsyncSession, ticker: str) -> CedearRatio | None:
    return await cedear_ratio_repository.get_latest(session, ticker)


# Returns all current ratios.
async def get_all_ratios(session: AsyncSession) -> list[CedearRatio]:
    return await cedear_ratio_repository.get_all_latest(session)


# Fetches CEDEAR ratios from Banco Comafi and stores them in the DB.
# Returns the number of ratios stored.
async def fetch_and_store_ratios(session: AsyncSession) -> int:
    results = await price_providers.fetch_comafi_ratios()
    if not results:
        logger.warning("No CEDEAR ratios returned from Comafi.")
        return 0

    today = date_type.today()
    count = 0
    for cedear_ticker, underlying, ratio_val in results:
        ratio = CedearRatio(
            ticker=cedear_ticker,
            underlying=underlying,
            ratio=ratio_val,
            effective_date=today,
            source=COMAFI_SOURCE,
        )
        await cedear_ratio_repository.upsert(session, ratio)
        count += 1

    logger.info("Stored %d CEDEAR ratios from Comafi.", count)
    return count
