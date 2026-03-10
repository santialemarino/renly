from fastapi import APIRouter

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.investment import Currency
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


# Returns current user's settings (display_currencies, default_currency).
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
    if "display_currencies" in payload:
        display = payload["display_currencies"]
        kwargs["display_currencies"] = [Currency(c) for c in display if c in Currency.__members__]
    if "default_currency" in payload:
        default = payload["default_currency"]
        kwargs["default_currency"] = Currency(default) if default in Currency.__members__ else None
    data = await settings_service.update_settings(session, current_user, **kwargs)
    return SettingsResponse(**data)
