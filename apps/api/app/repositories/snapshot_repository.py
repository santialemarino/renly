from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.snapshot import InvestmentSnapshot


# Lists snapshots for an investment, most recent first.
async def list_by_investment(
    session: AsyncSession,
    investment_id: int,
) -> list[InvestmentSnapshot]:
    result = await session.execute(
        select(InvestmentSnapshot)
        .where(InvestmentSnapshot.investment_id == investment_id)
        .order_by(InvestmentSnapshot.date.desc())
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


# Persists snapshot, commits, refreshes, and returns it (with id set).
async def create(session: AsyncSession, snapshot: InvestmentSnapshot) -> InvestmentSnapshot:
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


# Persists changes to an existing snapshot.
async def save(session: AsyncSession, snapshot: InvestmentSnapshot) -> None:
    session.add(snapshot)
    await session.commit()


# Namespace to call repository functions (e.g. snapshot_repository.list_by_investment).
class SnapshotRepository:
    list_by_investment = staticmethod(list_by_investment)
    get_by_investment_and_date = staticmethod(get_by_investment_and_date)
    create = staticmethod(create)
    save = staticmethod(save)


# Singleton used by services to access snapshot persistence.
snapshot_repository = SnapshotRepository()
