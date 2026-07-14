# Data access for asset prices.

from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.asset_price import AssetPrice
from app.models.utils import utcnow


# Returns the latest price for a ticker. Returns None if not found.
async def get_latest(session: AsyncSession, ticker: str) -> AssetPrice | None:
    result = await session.execute(select(AssetPrice).where(AssetPrice.ticker == ticker).order_by(AssetPrice.date.desc()).limit(1))
    return result.scalar_one_or_none()


# Returns {ticker: AssetPrice} for the latest stored price of each ticker.
async def get_latest_by_tickers(session: AsyncSession, tickers: list[str]) -> dict[str, AssetPrice]:
    if not tickers:
        return {}
    subq = (
        select(AssetPrice.ticker, func.max(AssetPrice.date).label("max_date"))
        .where(AssetPrice.ticker.in_(tickers))
        .group_by(AssetPrice.ticker)
        .subquery()
    )
    result = await session.execute(
        select(AssetPrice).join(
            subq,
            (AssetPrice.ticker == subq.c.ticker) & (AssetPrice.date == subq.c.max_date),
        )
    )
    return {p.ticker: p for p in result.scalars().all()}


# Returns a price by ticker and date. Returns None if not found.
async def get_by_ticker_and_date(
    session: AsyncSession,
    ticker: str,
    price_date: date_type,
) -> AssetPrice | None:
    result = await session.execute(
        select(AssetPrice).where(
            AssetPrice.ticker == ticker,
            AssetPrice.date == price_date,
        )
    )
    return result.scalar_one_or_none()


# Returns price history for a ticker, optionally filtered by date range.
async def get_history(
    session: AsyncSession,
    ticker: str,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> list[AssetPrice]:
    stmt = select(AssetPrice).where(AssetPrice.ticker == ticker)
    if start_date:
        stmt = stmt.where(AssetPrice.date >= start_date)
    if end_date:
        stmt = stmt.where(AssetPrice.date <= end_date)
    stmt = stmt.order_by(AssetPrice.date.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Bulk upserts multiple prices in a single statement. Returns the number of rows affected.
async def bulk_upsert(session: AsyncSession, prices: list[AssetPrice]) -> int:
    if not prices:
        return 0
    now = utcnow()
    values = [
        {
            "ticker": p.ticker,
            "date": p.date,
            "price": p.price,
            "currency": p.currency,
            "source": p.source,
            "updated_at": now,
        }
        for p in prices
    ]
    stmt = (
        insert(AssetPrice)
        .values(values)
        .on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={
                "price": insert(AssetPrice).excluded.price,
                "currency": insert(AssetPrice).excluded.currency,
                "source": insert(AssetPrice).excluded.source,
                "updated_at": insert(AssetPrice).excluded.updated_at,
            },
        )
    )
    await session.execute(stmt)
    return len(values)


# Namespace for asset price repository functions.
class AssetPriceRepository:
    bulk_upsert = staticmethod(bulk_upsert)
    get_by_ticker_and_date = staticmethod(get_by_ticker_and_date)
    get_history = staticmethod(get_history)
    get_latest = staticmethod(get_latest)
    get_latest_by_tickers = staticmethod(get_latest_by_tickers)


# Singleton used by services.
asset_price_repository = AssetPriceRepository()
