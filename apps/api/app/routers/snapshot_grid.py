# Endpoint for the snapshots grid (investments × months view).

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.domain.list_scope import ListScope
from app.domain.pot_monitoring import PotSeriesInterval
from app.models.investment import InvestmentCategory
from app.schemas.snapshot_grid import SnapshotGridResponse
from app.services import snapshot_grid_service

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


# Returns the snapshots grid: rows = investments, columns = one period end per bucket.
# Each cell contains value, period return, and transaction indicator.
# Pass currency to convert values (e.g. currency=ARS).
@router.get("/grid", response_model=SnapshotGridResponse)
async def get_snapshot_grid(
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency,
    scope: ListScope = Query(
        default=ListScope.private,
        description="Which scopes to return: private (own only, the default), shared (co-owned only) or all (both, grouped).",
    ),
    interval: PotSeriesInterval = Query(default=PotSeriesInterval.monthly, description="Column grid: monthly or weekly."),
    search: str | None = Query(default=None, description="Filter by investment name."),
    collection_ids: list[int] | None = Query(default=None, description="Filter by collection ids (union)."),
    category: InvestmentCategory | None = Query(default=None, description="Filter by category."),
    sort_by: str | None = Query(default=None, description="Sort field: name."),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction."),
) -> SnapshotGridResponse:
    return await snapshot_grid_service.get_snapshot_grid(
        session,
        current_user.id,
        scope=scope,
        interval=interval,
        search=search,
        collection_ids=collection_ids,
        category=category,
        currency=currency,
        sort_by=sort_by,
        sort_order=sort_order,
    )
