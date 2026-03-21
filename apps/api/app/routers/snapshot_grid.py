# Endpoint for the snapshots grid (investments × months view).

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.investment import InvestmentCategory
from app.schemas.snapshot_grid import SnapshotGridResponse
from app.services import snapshot_grid_service

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


# Returns the snapshots grid: rows = investments, columns = months.
# Each cell contains value, period return, and transaction indicator.
# TODO: Add optional currency query param for server-side conversion (like metrics endpoints).
@router.get("/grid", response_model=SnapshotGridResponse)
async def get_snapshot_grid(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter by investment name."),
    group_ids: list[int] | None = Query(default=None, description="Filter by group ids (union)."),
    category: InvestmentCategory | None = Query(default=None, description="Filter by category."),
) -> SnapshotGridResponse:
    return await snapshot_grid_service.get_snapshot_grid(
        session,
        current_user.id,
        search=search,
        group_ids=group_ids,
        category=category,
    )
