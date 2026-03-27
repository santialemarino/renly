# Data access for asset prices.

from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.asset_price import AssetPrice


# Returns the latest price for a ticker. Returns None if not found.
async def get_latest(session: AsyncSession, ticker: str) -> AssetPrice | None:
    result = await session.execute(
        select(AssetPrice).where(AssetPrice.ticker == ticker).order_by(AssetPrice.date.desc()).limit(1)
    )
    return result.scalar_one_or_none()


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


# Creates or updates a price by (ticker, date). Returns the persisted price.
async def upsert(session: AsyncSession, price: AssetPrice) -> AssetPrice:
    existing = await get_by_ticker_and_date(session, price.ticker, price.date)
    if existing:
        existing.price = price.price
        existing.currency = price.currency
        existing.source = price.source
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing
    session.add(price)
    await session.commit()
    await session.refresh(price)
    return price


# Namespace for asset price repository functions.
class AssetPriceRepository:
    get_latest = staticmethod(get_latest)
    get_by_ticker_and_date = staticmethod(get_by_ticker_and_date)
    get_history = staticmethod(get_history)
    upsert = staticmethod(upsert)


# Singleton used by services.
asset_price_repository = AssetPriceRepository()
