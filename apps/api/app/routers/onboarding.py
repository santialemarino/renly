from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.onboarding import OnboardingStatusResponse, SampleEntity
from app.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# Returns first-run onboarding status: checklist step completion + per-section sample flags, all
# derived from the user's real data.
@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: CurrentUser,
    session: SessionDep,
) -> OnboardingStatusResponse:
    data = await onboarding_service.get_status(session, current_user)
    return OnboardingStatusResponse(**data)


# Retires (permanently hides) a section's first-run sample when the user clears it.
@router.post("/samples/{entity}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_sample(
    entity: SampleEntity,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await onboarding_service.dismiss_sample(session, current_user, entity.value)


# Marks the first-run welcome tour completed (on finish or skip) so it never auto-shows again.
@router.post("/tour/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_tour(
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await onboarding_service.complete_tour(session, current_user)
