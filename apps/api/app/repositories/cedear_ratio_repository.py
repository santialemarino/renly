# Data access for CEDEAR ratios.

from decimal import Decimal

from sqlalchemy import and_, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.cedear_ratio import CedearRatio
from app.models.utils import utcnow


# Returns {ticker: ratio} for all given tickers (latest effective_date each).
async def get_latest_by_tickers(session: AsyncSession, tickers: list[str]) -> dict[str, Decimal]:
    if not tickers:
        return {}
    subq = (
        select(CedearRatio.ticker, func.max(CedearRatio.effective_date).label("max_date"))
        .where(CedearRatio.ticker.in_(tickers))
        .group_by(CedearRatio.ticker)
        .subquery()
    )
    result = await session.execute(
        select(CedearRatio).join(
            subq,
            and_(CedearRatio.ticker == subq.c.ticker, CedearRatio.effective_date == subq.c.max_date),
        )
    )
    return {r.ticker: r.ratio for r in result.scalars().all()}


# Bulk upserts multiple ratios in a single statement by (ticker, effective_date). Rows must be
# pre-deduped on that key — one statement can't update a conflict target twice. Returns the row count.
async def bulk_upsert(session: AsyncSession, ratios: list[CedearRatio]) -> int:
    if not ratios:
        return 0
    now = utcnow()
    values = [
        {
            "ticker": r.ticker,
            "underlying": r.underlying,
            "ratio": r.ratio,
            "effective_date": r.effective_date,
            "source": r.source,
            "updated_at": now,
        }
        for r in ratios
    ]
    stmt = (
        insert(CedearRatio)
        .values(values)
        .on_conflict_do_update(
            index_elements=["ticker", "effective_date"],
            set_={
                "underlying": insert(CedearRatio).excluded.underlying,
                "ratio": insert(CedearRatio).excluded.ratio,
                "source": insert(CedearRatio).excluded.source,
                "updated_at": insert(CedearRatio).excluded.updated_at,
            },
        )
    )
    await session.execute(stmt)
    return len(values)


# Namespace for CEDEAR ratio repository functions.
class CedearRatioRepository:
    bulk_upsert = staticmethod(bulk_upsert)
    get_latest_by_tickers = staticmethod(get_latest_by_tickers)


# Singleton used by services.
cedear_ratio_repository = CedearRatioRepository()
