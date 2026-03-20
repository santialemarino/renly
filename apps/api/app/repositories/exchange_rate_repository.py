# Data access for exchange rates.

from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair


# Returns the latest rate for each pair. {pair: ExchangeRate}.
async def get_latest_all(session: AsyncSession) -> dict[ExchangeRatePair, ExchangeRate]:
    subq = (
        select(
            ExchangeRate.pair,
            func.max(ExchangeRate.date).label("max_date"),
        )
        .group_by(ExchangeRate.pair)
        .subquery()
    )
    result = await session.execute(
        select(ExchangeRate).join(
            subq,
            (ExchangeRate.pair == subq.c.pair) & (ExchangeRate.date == subq.c.max_date),
        )
    )
    rates = result.scalars().all()
    return {r.pair: r for r in rates}


# Returns all rates for a specific date.
async def get_by_date(
    session: AsyncSession,
    rate_date: date_type,
) -> list[ExchangeRate]:
    result = await session.execute(
        select(ExchangeRate).where(ExchangeRate.date == rate_date).order_by(ExchangeRate.pair)
    )
    return list(result.scalars().all())


# Returns a rate by date and pair. Returns None if not found.
async def get_by_date_and_pair(
    session: AsyncSession,
    rate_date: date_type,
    pair: ExchangeRatePair,
) -> ExchangeRate | None:
    result = await session.execute(
        select(ExchangeRate).where(
            ExchangeRate.date == rate_date,
            ExchangeRate.pair == pair,
        )
    )
    return result.scalar_one_or_none()


# Creates or updates a rate by (date, pair). Returns the persisted rate.
async def upsert(session: AsyncSession, rate: ExchangeRate) -> ExchangeRate:
    existing = await get_by_date_and_pair(session, rate.date, rate.pair)
    if existing:
        existing.rate = rate.rate
        existing.source = rate.source
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing
    session.add(rate)
    await session.commit()
    await session.refresh(rate)
    return rate


# Namespace to call repository functions (e.g. exchange_rate_repository.get_latest_all).
class ExchangeRateRepository:
    get_latest_all = staticmethod(get_latest_all)
    get_by_date = staticmethod(get_by_date)
    get_by_date_and_pair = staticmethod(get_by_date_and_pair)
    upsert = staticmethod(upsert)


# Singleton used by services to access exchange rate persistence.
exchange_rate_repository = ExchangeRateRepository()
