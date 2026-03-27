# Endpoint for the snapshots grid (investments × months view).

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.investment import InvestmentCategory
from app.repositories import user_settings_repository
from app.schemas.snapshot_grid import SnapshotGridResponse
from app.services import snapshot_grid_service
from app.services.settings_service import DOLLAR_RATE_DEFAULT, SETTINGS_KEY_DOLLAR_RATE_PREFERENCE

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


# Reads the user's dollar rate preference from settings. Returns default if not set.
async def _get_dollar_pref(session, user_id: int) -> str:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    if row and row.settings:
        pref = row.settings.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
        if isinstance(pref, str) and pref:
            return pref
    return DOLLAR_RATE_DEFAULT


# Returns the snapshots grid: rows = investments, columns = months.
# Each cell contains value, period return, and transaction indicator.
# Pass currency to convert values (e.g. currency=ARS).
@router.get("/grid", response_model=SnapshotGridResponse)
async def get_snapshot_grid(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter by investment name."),
    group_ids: list[int] | None = Query(default=None, description="Filter by group ids (union)."),
    category: InvestmentCategory | None = Query(default=None, description="Filter by category."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
    sort_by: str | None = Query(default=None, description="Sort field: name."),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction."),
) -> SnapshotGridResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await snapshot_grid_service.get_snapshot_grid(
        session,
        current_user.id,
        search=search,
        group_ids=group_ids,
        category=category,
        currency=currency,
        dollar_preference=dp,
        sort_by=sort_by,
        sort_order=sort_order,
    )
