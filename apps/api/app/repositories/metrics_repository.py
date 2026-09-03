# Data access for metrics: bulk queries across investments, snapshots, and transactions.

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.domain.list_scope import ListScope
from app.models.investment import Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
from app.repositories.utils import scope_filter


# Returns all active investments for a user (no pagination), in the requested scope.
#
# `private` is the DEFAULT and every metrics caller keeps it: the investor dashboard stays private by
# decision (PR 8a decision 7 — a co-owned holding's TWR is the POT's, because your exposure moves
# whenever units are issued, so a per-investment return attributed to you is wrong in a way no label
# repairs). Only the snapshots grid asks for more, and it asks explicitly.
#
# Scope-major order (`pot_id` NULLS FIRST) for the same reason the two list queries take it: the grid
# draws a section header per scope and can only do that where the rows are contiguous.
async def list_active_investments(
    session: AsyncSession,
    user_id: int,
    pot_ids: list[int] | None = None,
    *,
    scope: ListScope = ListScope.private,
) -> list[Investment]:
    result = await session.execute(
        select(Investment)
        .where(scope_filter(Investment, user_id, pot_ids or [], scope), Investment.is_active.is_(True))
        .order_by(Investment.pot_id.nulls_first(), Investment.id)
    )
    return list(result.scalars().all())


# Returns the latest snapshot for each investment id. {investment_id: snapshot}.
async def get_latest_snapshots(
    session: AsyncSession,
    investment_ids: list[int],
) -> dict[int, InvestmentSnapshot]:
    if not investment_ids:
        return {}
    subq = (
        select(
            InvestmentSnapshot.investment_id,
            func.max(InvestmentSnapshot.date).label("max_date"),
        )
        .where(InvestmentSnapshot.investment_id.in_(investment_ids))
        .group_by(InvestmentSnapshot.investment_id)
        .subquery()
    )
    result = await session.execute(
        select(InvestmentSnapshot).join(
            subq,
            (InvestmentSnapshot.investment_id == subq.c.investment_id) & (InvestmentSnapshot.date == subq.c.max_date),
        )
    )
    snapshots = result.scalars().all()
    return {s.investment_id: s for s in snapshots}


# Returns all snapshots for the given investment ids, ordered by investment_id then date asc.
async def list_snapshots_by_investments(
    session: AsyncSession,
    investment_ids: list[int],
) -> list[InvestmentSnapshot]:
    if not investment_ids:
        return []
    result = await session.execute(
        select(InvestmentSnapshot)
        .where(InvestmentSnapshot.investment_id.in_(investment_ids))
        .order_by(InvestmentSnapshot.investment_id, InvestmentSnapshot.date.asc())
    )
    return list(result.scalars().all())


# Returns all transactions for the given investment ids, ordered by investment_id then date asc.
async def list_transactions_by_investments(
    session: AsyncSession,
    investment_ids: list[int],
) -> list[Transaction]:
    if not investment_ids:
        return []
    result = await session.execute(
        select(Transaction).where(Transaction.investment_id.in_(investment_ids)).order_by(Transaction.investment_id, Transaction.date.asc())
    )
    return list(result.scalars().all())


# Namespace to call repository functions (e.g. metrics_repository.list_active_investments).
class MetricsRepository:
    list_active_investments = staticmethod(list_active_investments)
    get_latest_snapshots = staticmethod(get_latest_snapshots)
    list_snapshots_by_investments = staticmethod(list_snapshots_by_investments)
    list_transactions_by_investments = staticmethod(list_transactions_by_investments)


# Singleton used by services to access metrics data access.
metrics_repository = MetricsRepository()
