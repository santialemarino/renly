# Data access for snapshots.

from datetime import date

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.snapshot import InvestmentSnapshot


# Returns True if the investment has at least one snapshot.
async def has_snapshots(session: AsyncSession, investment_id: int) -> bool:
    result = await session.execute(
        select(func.count()).select_from(InvestmentSnapshot).where(InvestmentSnapshot.investment_id == investment_id).limit(1)
    )
    return (result.scalar() or 0) > 0


# Returns the set of investment IDs that have at least one snapshot.
async def get_ids_with_snapshots(session: AsyncSession, investment_ids: list[int]) -> set[int]:
    if not investment_ids:
        return set()
    result = await session.execute(select(InvestmentSnapshot.investment_id).where(InvestmentSnapshot.investment_id.in_(investment_ids)).distinct())
    return {row[0] for row in result.all()}


# Lists snapshots for an investment, most recent first.
async def list_by_investment(
    session: AsyncSession,
    investment_id: int,
) -> list[InvestmentSnapshot]:
    result = await session.execute(
        select(InvestmentSnapshot).where(InvestmentSnapshot.investment_id == investment_id).order_by(InvestmentSnapshot.date.desc())
    )
    return list(result.scalars().all())


# Fetches a snapshot by investment and date. Returns None if not found.
async def get_by_investment_and_date(
    session: AsyncSession,
    investment_id: int,
    snapshot_date: date,
) -> InvestmentSnapshot | None:
    result = await session.execute(
        select(InvestmentSnapshot).where(
            InvestmentSnapshot.investment_id == investment_id,
            InvestmentSnapshot.date == snapshot_date,
        )
    )
    return result.scalar_one_or_none()


# Persists a new snapshot and flushes to get the id.
async def create(session: AsyncSession, snapshot: InvestmentSnapshot) -> InvestmentSnapshot:
    session.add(snapshot)
    await session.flush()
    return snapshot


# Persists changes to an existing snapshot.
async def save(session: AsyncSession, snapshot: InvestmentSnapshot) -> None:
    session.add(snapshot)


# Namespace to call repository functions (e.g. snapshot_repository.list_by_investment).
class SnapshotRepository:
    create = staticmethod(create)
    get_by_investment_and_date = staticmethod(get_by_investment_and_date)
    get_ids_with_snapshots = staticmethod(get_ids_with_snapshots)
    has_snapshots = staticmethod(has_snapshots)
    list_by_investment = staticmethod(list_by_investment)
    save = staticmethod(save)


# Singleton used by services to access snapshot persistence.
snapshot_repository = SnapshotRepository()
