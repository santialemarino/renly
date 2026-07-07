# Business logic for first-run onboarding.

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import expense_repository, income_repository, investment_repository
from app.services import settings_service


# Returns the first-run onboarding status. Each checklist step's done-state is derived from the
# user's real data (a cheap existence probe per entity + the stored primary-currency preference),
# so the checklist reflects the account's true state and self-heals — adding a first investment
# marks that step done, deleting everything reflects back to not-done — with no per-card flags.
# Also computes sample_mode: the first-run demo (client-rendered fixtures in empty sections) shows
# only for a pristine account that has never held real data and hasn't dismissed the samples.
async def get_status(session: AsyncSession, user: User) -> dict:
    has_investments = await investment_repository.exists_by_user(session, user.id)
    has_expenses = await expense_repository.exists_by_user(session, user.id)
    has_income = await income_repository.exists_by_user(session, user.id)
    current_settings = await settings_service.get_settings(session, user)

    has_any_data = has_investments or has_expenses or has_income
    has_ever_had_data = bool(current_settings["has_ever_had_data"])
    # Persist the "ever had data" marker the first time we observe real data, so first-run sample
    # mode never returns once the user has engaged — even after they later empty the account.
    if has_any_data and not has_ever_had_data:
        await settings_service.update_settings(session, user, has_ever_had_data=True)
        has_ever_had_data = True
    samples_dismissed = bool(current_settings["samples_dismissed"])
    sample_mode = not has_any_data and not has_ever_had_data and not samples_dismissed

    return {
        "has_investments": has_investments,
        "has_finances": has_expenses or has_income,
        "primary_currency_set": current_settings["primary_currency"] is not None,
        "sample_mode": sample_mode,
    }
