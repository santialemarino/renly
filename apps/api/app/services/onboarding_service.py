# Business logic for first-run onboarding.

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import expense_repository, income_repository, investment_repository
from app.services import settings_service


# Returns the first-run onboarding checklist status. Each step's done-state is derived from the
# user's real data (a cheap existence probe per entity + the stored primary-currency preference),
# so the checklist reflects the account's true state and self-heals — adding a first investment
# marks that step done, deleting everything reflects back to not-done — with no per-card flags.
async def get_status(session: AsyncSession, user: User) -> dict:
    has_investments = await investment_repository.exists_by_user(session, user.id)
    has_expenses = await expense_repository.exists_by_user(session, user.id)
    has_income = await income_repository.exists_by_user(session, user.id)
    current_settings = await settings_service.get_settings(session, user)
    return {
        "has_investments": has_investments,
        "has_finances": has_expenses or has_income,
        "primary_currency_set": current_settings["primary_currency"] is not None,
    }
