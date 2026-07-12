# Business logic for auto-generating snapshots from asset prices.
# For each ticker-linked investment, takes the last known quantity and multiplies by the
# current price to create a snapshot with source='auto'. Investments without a usable
# quantity, or whose latest price is quoted in a different currency than their base, are
# skipped (never guessed).

import calendar
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.asset_price import AssetPrice
from app.models.snapshot import InvestmentSnapshot
from app.repositories.investment_repository import investment_repository

logger = logging.getLogger(__name__)

SOURCE_AUTO = "auto"


# Creates auto-snapshots for all ticker-linked investments using latest prices.
# Batch-loads all required data upfront to avoid N+1 queries.
# Returns the number of snapshots created.
async def generate_auto_snapshots(session: AsyncSession) -> int:
    investments = await investment_repository.list_with_ticker(session)
    if not investments:
        return 0

    today = date_type.today()
    inv_ids = [inv.id for inv in investments]
    tickers = [inv.ticker for inv in investments if inv.ticker]

    # Batch-load: existing snapshots for today, latest prices, latest snapshots.
    existing_today = await _get_existing_snapshot_dates(session, inv_ids, today)
    latest_prices = await _get_latest_prices_by_ticker(session, tickers)
    latest_snapshots = await _get_latest_snapshots_by_investment(session, inv_ids)

    # Build all snapshots in memory, then bulk-add in one flush.
    snapshots: list[InvestmentSnapshot] = []
    for inv in investments:
        if inv.id in existing_today:
            continue

        price = latest_prices.get(inv.ticker)
        if price is None:
            logger.debug("No price data for %s — skipping auto-snapshot.", inv.ticker)
            continue

        last_snap = latest_snapshots.get(inv.id)
        quantity = last_snap.quantity if last_snap else None
        if quantity is None or quantity <= 0:
            # Without a usable quantity the snapshot would record the price of ONE share as the
            # whole position's value — skip and leave the user's manual value authoritative.
            logger.debug("No usable quantity for investment %s (%s) — skipping auto-snapshot.", inv.id, inv.ticker)
            continue
        if price.currency != inv.base_currency:
            # A price quoted in another currency would be stored unconverted under the base
            # label — skip rather than misvalue; no conversion attempt by design.
            logger.warning(
                "Price currency %s != base currency %s for investment %s (%s) — skipping auto-snapshot.",
                price.currency,
                inv.base_currency,
                inv.id,
                inv.ticker,
            )
            continue
        value = quantity * price.price

        snapshots.append(
            InvestmentSnapshot(
                investment_id=inv.id,
                user_id=inv.user_id,
                date=today,
                value=Decimal(str(round(value, 2))),
                quantity=quantity,
                currency=inv.base_currency,
                source=SOURCE_AUTO,
            )
        )

    if snapshots:
        session.add_all(snapshots)
        await session.commit()
        logger.info("Auto-snapshots: created %d snapshots for %s.", len(snapshots), today)
    return len(snapshots)


# Runs generate_auto_snapshots once if the most recent month-end tick was missed: now is within
# `catchup_days` after the last month-end fire time (month-end date at snapshots_hour_utc) AND no
# source='auto' snapshot exists dated on or after that month-end (the cron run or a previous
# catch-up would have left one). Snapshots created here are dated today — a few days late beats a
# missing month. Returns True when the catch-up actually ran. `now_utc` is injectable for tests.
async def run_startup_catchup(
    session: AsyncSession,
    *,
    catchup_days: int,
    snapshots_hour_utc: int,
    now_utc: datetime | None = None,
) -> bool:
    now_utc = now_utc or datetime.now(UTC)
    month_end = most_recent_month_end(now_utc.date())
    fire_at = datetime(month_end.year, month_end.month, month_end.day, snapshots_hour_utc, tzinfo=UTC)
    if now_utc < fire_at or now_utc - fire_at > timedelta(days=catchup_days):
        return False
    if await _has_auto_snapshots_since(session, month_end):
        return False
    await generate_auto_snapshots(session)
    return True


# Most recent month-end date at or before `today` (today itself when it IS a month's last day).
def most_recent_month_end(today: date_type) -> date_type:
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day == last_day:
        return today
    return today.replace(day=1) - timedelta(days=1)


# Returns the set of investment IDs that already have a snapshot for the given date.
async def _get_existing_snapshot_dates(session: AsyncSession, inv_ids: list[int], snapshot_date: date_type) -> set[int]:
    result = await session.execute(
        select(InvestmentSnapshot.investment_id).where(
            InvestmentSnapshot.investment_id.in_(inv_ids),
            InvestmentSnapshot.date == snapshot_date,
        )
    )
    return {row[0] for row in result.all()}


# Returns {ticker: AssetPrice} for the latest price of each ticker.
async def _get_latest_prices_by_ticker(session: AsyncSession, tickers: list[str]) -> dict[str, AssetPrice]:
    if not tickers:
        return {}
    # Get the max date per ticker, then join to get the full row.
    from sqlalchemy import func

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


# Returns {investment_id: latest InvestmentSnapshot} for each investment.
async def _get_latest_snapshots_by_investment(session: AsyncSession, inv_ids: list[int]) -> dict[int, InvestmentSnapshot]:
    if not inv_ids:
        return {}
    from sqlalchemy import func

    subq = (
        select(InvestmentSnapshot.investment_id, func.max(InvestmentSnapshot.date).label("max_date"))
        .where(InvestmentSnapshot.investment_id.in_(inv_ids))
        .group_by(InvestmentSnapshot.investment_id)
        .subquery()
    )
    result = await session.execute(
        select(InvestmentSnapshot).join(
            subq,
            (InvestmentSnapshot.investment_id == subq.c.investment_id) & (InvestmentSnapshot.date == subq.c.max_date),
        )
    )
    return {s.investment_id: s for s in result.scalars().all()}


# True when any auto-generated snapshot exists dated on or after `since` (LIMIT 1 probe).
async def _has_auto_snapshots_since(session: AsyncSession, since: date_type) -> bool:
    result = await session.execute(
        select(InvestmentSnapshot.id).where(InvestmentSnapshot.source == SOURCE_AUTO, InvestmentSnapshot.date >= since).limit(1)
    )
    return result.scalar_one_or_none() is not None
