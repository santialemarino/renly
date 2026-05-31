# Plan gating helpers — the monetization seam. Free at launch; Pro gates are wired here as paid features land.

from app.domain import PlanRequiredError
from app.models.user import User, UserPlan


# Raises PlanRequiredError unless the user is on the Pro plan; the seam for Pro-gated features.
def requires_pro(user: User) -> None:
    if user.plan != UserPlan.pro:
        raise PlanRequiredError()
