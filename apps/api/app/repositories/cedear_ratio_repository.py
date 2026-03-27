# Data access for CEDEAR ratios.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.cedear_ratio import CedearRatio


# Returns the current ratio for a CEDEAR ticker (latest by effective_date).
async def get_latest(session: AsyncSession, ticker: str) -> CedearRatio | None:
    result = await session.execute(
        select(CedearRatio).where(CedearRatio.ticker == ticker).order_by(CedearRatio.effective_date.desc()).limit(1)
    )
    return result.scalar_one_or_none()


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


# Creates or updates a ratio by (ticker, effective_date).
async def upsert(session: AsyncSession, ratio: CedearRatio) -> CedearRatio:
    result = await session.execute(
        select(CedearRatio).where(
            CedearRatio.ticker == ratio.ticker,
            CedearRatio.effective_date == ratio.effective_date,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.underlying = ratio.underlying
        existing.ratio = ratio.ratio
        existing.source = ratio.source
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing
    session.add(ratio)
    await session.commit()
    await session.refresh(ratio)
    return ratio


# Namespace for CEDEAR ratio repository functions.
class CedearRatioRepository:
    get_latest = staticmethod(get_latest)
    get_all_latest = staticmethod(get_all_latest)
    upsert = staticmethod(upsert)


# Singleton used by services.
cedear_ratio_repository = CedearRatioRepository()
