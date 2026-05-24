# Data access for exchange rates.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.utils import utcnow


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
    result = await session.execute(select(ExchangeRate).where(ExchangeRate.date == rate_date).order_by(ExchangeRate.pair))
    return list(result.scalars().all())


# Returns every stored rate, grouped by pair and sorted by date ascending. Powers the
# RateLookup helper for date-aware conversion (Phase 3, Step C). One query per request,
# bounded by the size of the exchange_rates table (small: ~5 pairs * ~5 years of daily
# rows = ~9k rows in practice).
async def get_all_grouped_by_pair(
    session: AsyncSession,
) -> dict[ExchangeRatePair, list[ExchangeRate]]:
    result = await session.execute(select(ExchangeRate).order_by(ExchangeRate.pair, ExchangeRate.date))
    grouped: dict[ExchangeRatePair, list[ExchangeRate]] = {}
    for rate in result.scalars().all():
        grouped.setdefault(rate.pair, []).append(rate)
    return grouped


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


# Creates or updates a single rate by (date, pair) using ON CONFLICT.
async def upsert(session: AsyncSession, rate: ExchangeRate) -> None:
    now = utcnow()
    stmt = (
        insert(ExchangeRate)
        .values(
            date=rate.date,
            pair=rate.pair,
            rate=rate.rate,
            source=rate.source,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["date", "pair"],
            set_={
                "rate": rate.rate,
                "source": rate.source,
                "updated_at": now,
            },
        )
    )
    await session.execute(stmt)


# Bulk upserts multiple rates in a single statement. Returns the number of rows affected.
async def bulk_upsert(
    session: AsyncSession,
    rates: list[tuple[ExchangeRatePair, Decimal, str]],
    rate_date: date_type,
) -> int:
    if not rates:
        return 0
    now = utcnow()
    values = [{"date": rate_date, "pair": pair, "rate": rate, "source": source, "updated_at": now} for pair, rate, source in rates]
    stmt = (
        insert(ExchangeRate)
        .values(values)
        .on_conflict_do_update(
            index_elements=["date", "pair"],
            set_={
                "rate": insert(ExchangeRate).excluded.rate,
                "source": insert(ExchangeRate).excluded.source,
                "updated_at": insert(ExchangeRate).excluded.updated_at,
            },
        )
    )
    await session.execute(stmt)
    return len(values)


# Namespace to call repository functions (e.g. exchange_rate_repository.get_latest_all).
class ExchangeRateRepository:
    bulk_upsert = staticmethod(bulk_upsert)
    get_all_grouped_by_pair = staticmethod(get_all_grouped_by_pair)
    get_by_date = staticmethod(get_by_date)
    get_by_date_and_pair = staticmethod(get_by_date_and_pair)
    get_latest_all = staticmethod(get_latest_all)
    upsert = staticmethod(upsert)


# Singleton used by services to access exchange rate persistence.
exchange_rate_repository = ExchangeRateRepository()
