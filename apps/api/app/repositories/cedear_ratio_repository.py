# Data access for CEDEAR ratios.

from decimal import Decimal

from sqlalchemy import and_, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.cedear_ratio import CedearRatio
from app.models.utils import utcnow


# Returns the current ratio for a CEDEAR ticker (latest by effective_date).
async def get_latest(session: AsyncSession, ticker: str) -> CedearRatio | None:
    result = await session.execute(select(CedearRatio).where(CedearRatio.ticker == ticker).order_by(CedearRatio.effective_date.desc()).limit(1))
    return result.scalar_one_or_none()


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


# Returns all current ratios (latest effective_date per ticker).
async def get_all_latest(session: AsyncSession) -> list[CedearRatio]:
    # For the small dataset (~30 CEDEARs), fetch all and deduplicate in Python.
    result = await session.execute(select(CedearRatio).order_by(CedearRatio.ticker, CedearRatio.effective_date.desc()))
    all_ratios = result.scalars().all()
    seen: set[str] = set()
    latest: list[CedearRatio] = []
    for r in all_ratios:
        if r.ticker not in seen:
            seen.add(r.ticker)
            latest.append(r)
    return latest


# Creates or updates a single ratio by (ticker, effective_date) using ON CONFLICT.
async def upsert(session: AsyncSession, ratio: CedearRatio) -> None:
    now = utcnow()
    stmt = (
        insert(CedearRatio)
        .values(
            ticker=ratio.ticker,
            underlying=ratio.underlying,
            ratio=ratio.ratio,
            effective_date=ratio.effective_date,
            source=ratio.source,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["ticker", "effective_date"],
            set_={
                "underlying": ratio.underlying,
                "ratio": ratio.ratio,
                "source": ratio.source,
                "updated_at": now,
            },
        )
    )
    await session.execute(stmt)


# Namespace for CEDEAR ratio repository functions.
class CedearRatioRepository:
    get_all_latest = staticmethod(get_all_latest)
    get_latest = staticmethod(get_latest)
    get_latest_by_tickers = staticmethod(get_latest_by_tickers)
    upsert = staticmethod(upsert)


# Singleton used by services.
cedear_ratio_repository = CedearRatioRepository()
