# Business logic for auto-generating snapshots from asset prices.
# For each ticker-linked investment, takes the last known quantity
# and multiplies by the current price to create a snapshot with source='auto'.

import logging
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment import Investment
from app.models.snapshot import InvestmentSnapshot
from app.repositories.asset_price_repository import asset_price_repository
from app.repositories.investment_repository import investment_repository
from app.repositories.snapshot_repository import snapshot_repository

logger = logging.getLogger(__name__)

SOURCE_AUTO = "auto"


# Creates auto-snapshots for all ticker-linked investments using latest prices.
# Returns the number of snapshots created.
async def generate_auto_snapshots(session: AsyncSession) -> int:
    investments = await investment_repository.list_with_ticker(session)
    today = date_type.today()
    count = 0

    for inv in investments:
        try:
            created = await _generate_for_investment(session, inv, today)
            if created:
                count += 1
        except Exception:
            logger.exception("Auto-snapshot failed for %s (%s).", inv.ticker, inv.name)

    if count:
        logger.info("Auto-snapshots: created %d snapshots for %s.", count, today)
    return count


# Creates an auto-snapshot for a single investment. Returns True if created.
async def _generate_for_investment(
    session: AsyncSession,
    inv: Investment,
    snapshot_date: date_type,
) -> bool:
    # Skip if a snapshot already exists for this date (manual or auto).
    existing = await snapshot_repository.get_by_investment_and_date(session, inv.id, snapshot_date)
    if existing is not None:
        return False

    # Get the latest price for this ticker.
    latest_price = await asset_price_repository.get_latest(session, inv.ticker)
    if latest_price is None:
        logger.debug("No price data for %s — skipping auto-snapshot.", inv.ticker)
        return False

    # Get the last known quantity from the most recent snapshot.
    last_snapshot = await _get_latest_snapshot(session, inv.id)
    quantity = last_snapshot.quantity if last_snapshot else None

    # Compute value: quantity x price, or just use the price as value if no quantity.
    if quantity is not None and quantity > 0:
        value = quantity * latest_price.price
    else:
        value = latest_price.price

    snapshot = InvestmentSnapshot(
        investment_id=inv.id,
        date=snapshot_date,
        value=Decimal(str(round(value, 2))),
        quantity=quantity,
        currency=inv.base_currency,
        source=SOURCE_AUTO,
    )
    await snapshot_repository.create(session, snapshot)
    return True


# Returns the most recent snapshot for an investment. Returns None if none exist.
async def _get_latest_snapshot(
    session: AsyncSession,
    investment_id: int,
) -> InvestmentSnapshot | None:
    from sqlmodel import select

    result = await session.execute(
        select(InvestmentSnapshot)
        .where(InvestmentSnapshot.investment_id == investment_id)
        .order_by(InvestmentSnapshot.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
