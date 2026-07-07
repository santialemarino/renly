from fastapi import APIRouter

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


# Returns current user's settings (currencies, period presets, limits).
@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: JwtOrApiKeyUser,
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
    if "dollar_rate_preference" in payload:
        kwargs["dollar_rate_preference"] = payload["dollar_rate_preference"]
    if "shortcut_currencies" in payload:
        kwargs["shortcut_currencies"] = payload["shortcut_currencies"]
    if "timezone" in payload:
        kwargs["timezone"] = payload["timezone"]
    if "timezone_mode" in payload:
        kwargs["timezone_mode"] = payload["timezone_mode"]
    if "language" in payload:
        kwargs["language"] = payload["language"]
    if "language_mode" in payload:
        kwargs["language_mode"] = payload["language_mode"]
    if "liquidity_threshold_pct" in payload:
        kwargs["liquidity_threshold_pct"] = payload["liquidity_threshold_pct"]
    if "savings_rate_healthy_pct" in payload:
        kwargs["savings_rate_healthy_pct"] = payload["savings_rate_healthy_pct"]
    if "savings_rate_moderate_pct" in payload:
        kwargs["savings_rate_moderate_pct"] = payload["savings_rate_moderate_pct"]
    if "income_expense_ratio_healthy" in payload:
        kwargs["income_expense_ratio_healthy"] = payload["income_expense_ratio_healthy"]
    if "onboarding_completed" in payload:
        kwargs["onboarding_completed"] = payload["onboarding_completed"]
    data = await settings_service.update_settings(session, current_user, **kwargs)
    return SettingsResponse(**data)
