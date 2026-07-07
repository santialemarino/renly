# Response schema for the onboarding status endpoint (HTTP contract).

from pydantic import BaseModel, Field


# Response for GET /onboarding/status. First-run checklist completion, each step derived from the
# user's real data (not per-card "clicked" flags) so the checklist reflects the account's true state.
class OnboardingStatusResponse(BaseModel):
    has_investments: bool = Field(
        description="Whether the user has created at least one investment.",
    )
    has_finances: bool = Field(
        description="Whether the user has recorded at least one income or expense entry.",
    )
    primary_currency_set: bool = Field(
        description="Whether the user has explicitly chosen a primary display currency.",
    )
    sample_mode: bool = Field(
        description="Whether first-run sample data should be shown (pristine account: never held real data, samples not dismissed).",
    )
