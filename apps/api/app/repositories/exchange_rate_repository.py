# Data access for exchange rates.

from datetime import date as date_type
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.domain.currency import RatePoint
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.utils import utcnow

# Rows per INSERT statement: six bind parameters a row keeps a chunk far below asyncpg's 32,767 cap.
WRITE_CHUNK_SIZE = 1000


# One row to write: a pair's rate on a date, and the source that quoted it.
class ExchangeRateRow(NamedTuple):
    date: date_type
    pair: ExchangeRatePair
    rate: Decimal
    source: str


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


# Returns every rate dated in [start, end] (all pairs), ordered by pair then date.
async def get_by_date_range(
    session: AsyncSession,
    start: date_type,
    end: date_type,
) -> list[ExchangeRate]:
    result = await session.execute(
        select(ExchangeRate).where(ExchangeRate.date >= start, ExchangeRate.date <= end).order_by(ExchangeRate.pair, ExchangeRate.date)
    )
    return list(result.scalars().all())


# Returns every stored rate as (date, rate), grouped by pair and sorted by date ascending. Powers the
# RateLookup helper for date-aware conversion. One query, three columns, no ORM rows: the table holds one
# row per pair per quoted day since 2011 (~23k rows).
async def get_all_grouped_by_pair(
    session: AsyncSession,
) -> dict[ExchangeRatePair, list[RatePoint]]:
    result = await session.execute(select(ExchangeRate.pair, ExchangeRate.date, ExchangeRate.rate).order_by(ExchangeRate.pair, ExchangeRate.date))
    grouped: dict[ExchangeRatePair, list[RatePoint]] = {}
    for pair, rate_date, rate in result.all():
        grouped.setdefault(pair, []).append(RatePoint(rate_date, rate))
    return grouped


# Returns the number of stored rates per pair, with each pair's first and last date. {pair: (count, first, last)}.
async def get_coverage_by_pair(session: AsyncSession) -> dict[ExchangeRatePair, tuple[int, date_type, date_type]]:
    result = await session.execute(
        select(ExchangeRate.pair, func.count(), func.min(ExchangeRate.date), func.max(ExchangeRate.date)).group_by(ExchangeRate.pair)
    )
    return {pair: (count, first, last) for pair, count, first, last in result.all()}


# Inserts the rows whose (date, pair) is not stored yet and leaves every existing row untouched
# (ON CONFLICT DO NOTHING), so a second run over the same quotes inserts nothing. One statement per
# WRITE_CHUNK_SIZE rows keeps a full backfill under asyncpg's bind-parameter cap. Returns the number
# of rows inserted.
async def bulk_insert_missing(
    session: AsyncSession,
    rows: list[ExchangeRateRow],
) -> int:
    inserted = 0
    now = utcnow()
    for start in range(0, len(rows), WRITE_CHUNK_SIZE):
        chunk = rows[start : start + WRITE_CHUNK_SIZE]
        values = [{"date": r.date, "pair": r.pair, "rate": r.rate, "source": r.source, "created_at": now, "updated_at": now} for r in chunk]
        stmt = insert(ExchangeRate).values(values).on_conflict_do_nothing(index_elements=["date", "pair"]).returning(ExchangeRate.id)
        result = await session.execute(stmt)
        inserted += len(result.scalars().all())
    return inserted


# Upserts rows by (date, pair): a stored row for the same date and pair takes the new rate and source.
# Used for the latest quotes (the last quote of a day wins) and for repairing a provably misdated row.
# Returns the number of rows written.
async def bulk_upsert(
    session: AsyncSession,
    rows: list[ExchangeRateRow],
) -> int:
    now = utcnow()
    for start in range(0, len(rows), WRITE_CHUNK_SIZE):
        chunk = rows[start : start + WRITE_CHUNK_SIZE]
        values = [{"date": r.date, "pair": r.pair, "rate": r.rate, "source": r.source, "updated_at": now} for r in chunk]
        stmt = insert(ExchangeRate).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "pair"],
            set_={
                "rate": stmt.excluded.rate,
                "source": stmt.excluded.source,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
    return len(rows)


# Namespace to call repository functions (e.g. exchange_rate_repository.get_latest_all).
class ExchangeRateRepository:
    bulk_insert_missing = staticmethod(bulk_insert_missing)
    bulk_upsert = staticmethod(bulk_upsert)
    get_all_grouped_by_pair = staticmethod(get_all_grouped_by_pair)
    get_by_date = staticmethod(get_by_date)
    get_by_date_range = staticmethod(get_by_date_range)
    get_coverage_by_pair = staticmethod(get_coverage_by_pair)
    get_latest_all = staticmethod(get_latest_all)


# Singleton used by services to access exchange rate persistence.
exchange_rate_repository = ExchangeRateRepository()
