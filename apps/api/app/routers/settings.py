from fastapi import APIRouter

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


# Returns current user's settings (primary_currency, secondary_currency).
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
    data = await settings_service.update_settings(session, current_user, **kwargs)
    return SettingsResponse(**data)
