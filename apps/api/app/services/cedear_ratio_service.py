# Business logic for CEDEAR ratios: fetching from providers and storing in the DB.
# Fetches both Comafi (Excel) and BYMA (PDF) in parallel, picks the most complete source.

import asyncio
import logging
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cedear_ratio import CedearRatio
from app.repositories.cedear_ratio_repository import cedear_ratio_repository
from app.services import price_providers
from app.services.price_providers import BYMA_SOURCE, COMAFI_SOURCE

logger = logging.getLogger(__name__)


# Picks the best ratio source: newer date wins, then more entries, then Comafi preferred.
def _pick_best(
    comafi: price_providers.RatioResult,
    comafi_date: date_type | None,
    byma: price_providers.RatioResult,
    byma_date: date_type | None,
) -> tuple[price_providers.RatioResult, str]:
    has_comafi = len(comafi) > 0
    has_byma = len(byma) > 0

    if has_comafi and has_byma:
        # Both have data — compare dates first.
        if comafi_date and byma_date and comafi_date != byma_date:
            if byma_date > comafi_date:
                logger.info("Using BYMA (date %s > Comafi %s).", byma_date, comafi_date)
                return byma, BYMA_SOURCE
            logger.info("Using Comafi (date %s >= BYMA %s).", comafi_date, byma_date)
            return comafi, COMAFI_SOURCE
        # Dates equal or unknown — more entries wins.
        if len(byma) > len(comafi):
            logger.info("Using BYMA (%d > Comafi %d entries).", len(byma), len(comafi))
            return byma, BYMA_SOURCE
        # Tied or Comafi has more — Comafi preferred (authoritative issuer).
        logger.info("Using Comafi (%d entries, preferred source).", len(comafi))
        return comafi, COMAFI_SOURCE

    if has_comafi:
        logger.info("Using Comafi (%d entries). BYMA returned nothing.", len(comafi))
        return comafi, COMAFI_SOURCE
    if has_byma:
        logger.info("Using BYMA (%d entries). Comafi returned nothing.", len(byma))
        return byma, BYMA_SOURCE

    return [], COMAFI_SOURCE


# Fetches CEDEAR ratios from both Comafi and BYMA in parallel, picks the best source, and stores.
# Selection: newer date wins → more entries breaks ties → Comafi preferred if still tied.
# Returns the number of ratios stored.
async def fetch_and_store_ratios(session: AsyncSession) -> int:
    comafi_fetch, byma_fetch = await asyncio.gather(
        price_providers.fetch_comafi_ratios(),
        price_providers.fetch_byma_ratios(),
        return_exceptions=True,
    )

    # Normalize exceptions to empty results.
    empty = price_providers.RatioFetchResult([], None)
    if isinstance(comafi_fetch, BaseException):
        logger.warning("Comafi fetch raised an exception: %s", comafi_fetch)
        comafi_fetch = empty
    if isinstance(byma_fetch, BaseException):
        logger.warning("BYMA fetch raised an exception: %s", byma_fetch)
        byma_fetch = empty

    comafi_ratios, comafi_date = comafi_fetch
    byma_ratios, byma_date = byma_fetch

    logger.info(
        "Fetched ratios — Comafi: %d (date: %s), BYMA: %d (date: %s).",
        len(comafi_ratios),
        comafi_date,
        len(byma_ratios),
        byma_date,
    )

    # Pick the best source: newer date → more entries → Comafi preferred.
    results, source = _pick_best(comafi_ratios, comafi_date, byma_ratios, byma_date)
    if not results:
        logger.warning("Both Comafi and BYMA returned no CEDEAR ratios.")
        return 0

    today = date_type.today()
    # Dedupe by ticker (last entry wins, matching the old per-row upsert order) — all rows share
    # effective_date=today, and bulk_upsert requires unique (ticker, effective_date) rows.
    deduped = {cedear_ticker: (underlying, ratio_val) for cedear_ticker, underlying, ratio_val in results}
    ratios = [
        CedearRatio(ticker=ticker, underlying=underlying, ratio=ratio_val, effective_date=today, source=source)
        for ticker, (underlying, ratio_val) in deduped.items()
    ]
    stored = await cedear_ratio_repository.bulk_upsert(session, ratios)

    await session.commit()
    logger.info("Stored %d CEDEAR ratios from %s.", stored, source)
    return stored
