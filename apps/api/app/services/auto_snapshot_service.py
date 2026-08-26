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

from app.models.snapshot import InvestmentSnapshot
from app.repositories.asset_price_repository import asset_price_repository
from app.repositories.investment_repository import investment_repository
from app.repositories.snapshot_repository import snapshot_repository

logger = logging.getLogger(__name__)

SOURCE_AUTO = "auto"


# Creates auto-snapshots for all ticker-linked investments using latest prices.
# Batch-loads all required data upfront to avoid N+1 queries.
# Returns the number of snapshots created.
async def generate_auto_snapshots(session: AsyncSession) -> int:
    investments = await investment_repository.list_with_ticker(session)
    if not investments:
        return 0

    # Server-local date on purpose: auto-snapshots are one global batch (a single date for all
    # users, deduped per investment per date). Per-user local dates would split the batch and
    # the existing-snapshot dedup key. User-facing "today" semantics live in request paths.
    today = date_type.today()
    inv_ids = [inv.id for inv in investments]
    tickers = [inv.ticker for inv in investments if inv.ticker]

    # Batch-load: existing snapshots for today, latest prices, latest snapshots.
    existing_today = await snapshot_repository.get_ids_with_snapshot_on_date(session, inv_ids, today)
    latest_prices = await asset_price_repository.get_latest_by_tickers(session, tickers)
    latest_snapshots = await snapshot_repository.get_latest_by_investments(session, inv_ids)

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
                # Scope inherited from the parent, both halves. list_with_ticker is a GLOBAL query
                # (the scheduler runs as the owner, across every user), so it picks up co-owned
                # investments too — and one of those with user_id NULL and no pot_id violates the
                # single-owner CHECK, which would fail the whole batch for everyone, not just them.
                investment_id=inv.id,
                user_id=inv.user_id,
                pot_id=inv.pot_id,
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


# True when any auto-generated snapshot exists dated on or after `since` (LIMIT 1 probe).
async def _has_auto_snapshots_since(session: AsyncSession, since: date_type) -> bool:
    result = await session.execute(
        select(InvestmentSnapshot.id).where(InvestmentSnapshot.source == SOURCE_AUTO, InvestmentSnapshot.date >= since).limit(1)
    )
    return result.scalar_one_or_none() is not None
