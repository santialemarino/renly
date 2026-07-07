from fastapi import APIRouter

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.onboarding import OnboardingStatusResponse
from app.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# Returns first-run onboarding checklist status (step completion derived from the user's real data).
@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: CurrentUser,
    session: SessionDep,
) -> OnboardingStatusResponse:
    data = await onboarding_service.get_status(session, current_user)
    return OnboardingStatusResponse(**data)
