# Request/response schemas for the onboarding endpoints (HTTP contract).

from enum import StrEnum

from pydantic import BaseModel, Field


# The sections that render a first-run sample; the value is the entity key used in settings + routing.
class SampleEntity(StrEnum):
    INVESTMENTS = "investments"
    EXPENSES = "expenses"
    INCOME = "income"


# Response for GET /onboarding/status. First-run checklist completion plus per-section sample flags,
# each derived from the user's real data (not per-card "clicked" flags).
class OnboardingStatusResponse(BaseModel):
    has_investments: bool = Field(
        description="Whether the user has created at least one investment.",
    )
    has_finances: bool = Field(
        description="Whether the user has recorded at least one income or expense entry.",
    )
    has_accounts: bool = Field(
        description="Whether the user has created at least one cash or bank account.",
    )
    primary_currency_set: bool = Field(
        description="Whether the user has explicitly chosen a primary display currency.",
    )
    sample_investments: bool = Field(
        description="Whether the investments section should show its first-run sample data.",
    )
    sample_expenses: bool = Field(
        description="Whether the expenses section should show its first-run sample data.",
    )
    sample_income: bool = Field(
        description="Whether the income section should show its first-run sample data.",
    )
    tour_completed: bool = Field(
        description="Whether the user has finished or dismissed the first-run welcome tour.",
    )
