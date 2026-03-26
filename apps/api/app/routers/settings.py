from fastapi import APIRouter

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


# Returns current user's settings (currencies, period presets, limits).
@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: CurrentUser,
    session: SessionDep,
) -> SettingsResponse:
    data = await settings_service.get_settings(session, current_user)
    return SettingsResponse(**data)


# Updates settings. Partial; only provided fields are updated.
@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SettingsResponse:
    payload = body.model_dump(exclude_unset=True)
    kwargs = {}
    if "primary_currency" in payload:
        kwargs["primary_currency"] = payload["primary_currency"]
    if "secondary_currency" in payload:
        kwargs["secondary_currency"] = payload["secondary_currency"]
    if "preferred_currencies" in payload:
        kwargs["preferred_currencies"] = payload["preferred_currencies"]
    if "period_presets" in payload:
        kwargs["period_presets"] = payload["period_presets"]
    if "max_groups" in payload:
        kwargs["max_groups"] = payload["max_groups"]
    if "group_warning_pct" in payload:
        kwargs["group_warning_pct"] = payload["group_warning_pct"]
    data = await settings_service.update_settings(session, current_user, **kwargs)
    return SettingsResponse(**data)
