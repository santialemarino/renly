# Business logic for first-run onboarding.

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import expense_repository, income_repository, investment_repository
from app.services import settings_service

logger = logging.getLogger(__name__)


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
    # The marker is latched primarily at data-creation time (see the create services). This is a
    # best-effort backstop for data that entered outside those paths (import / restore / scheduler):
    # if we observe data but the marker is unset, latch it atomically so it survives a later empty
    # account. Swallow failures so a write hiccup degrades to a correct read, never a failed GET.
    if has_any_data and not has_ever_had_data:
        try:
            await settings_service.mark_has_ever_had_data(session, user.id)
            await session.commit()
            has_ever_had_data = True
        except Exception:
            logger.warning("Could not latch has_ever_had_data for user %s", user.id, exc_info=True)
            await session.rollback()
    samples_dismissed = bool(current_settings["samples_dismissed"])
    sample_mode = not has_any_data and not has_ever_had_data and not samples_dismissed

    return {
        "has_investments": has_investments,
        "has_finances": has_expenses or has_income,
        "primary_currency_set": current_settings["primary_currency"] is not None,
        "sample_mode": sample_mode,
    }
