# Business logic for first-run onboarding.

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import account_repository, expense_repository, income_repository, investment_repository
from app.services import settings_service

logger = logging.getLogger(__name__)


# Returns the first-run onboarding status. Each checklist step's done-state is derived from the
# user's real data (a cheap existence probe per entity + the stored primary-currency preference),
# so the checklist reflects the account's true state and self-heals. Also computes the per-section
# first-run samples: a section shows its client-rendered sample only while the user has no data of
# that entity AND hasn't retired it (retired = created that entity once, or cleared the sample), so
# each section teaches once, independently. The retire is latched primarily at creation time (see
# the create services); this backstops data that entered outside those paths (import / restore /
# scheduler) by retiring any entity that already has data.
async def get_status(session: AsyncSession, user: User) -> dict:
    has_investments = await investment_repository.exists_by_user(session, user.id)
    has_accounts = await account_repository.exists_by_user(session, user.id)
    has_expenses = await expense_repository.exists_by_user(session, user.id)
    has_income = await income_repository.exists_by_user(session, user.id)
    current_settings = await settings_service.get_settings(session, user)
    retired = current_settings["samples_retired"]

    has_data = {"investments": has_investments, "expenses": has_expenses, "income": has_income}
    to_retire = [entity for entity, present in has_data.items() if present and not retired[entity]]
    if to_retire:
        try:
            for entity in to_retire:
                await settings_service.retire_sample(session, user.id, entity)
            await session.commit()
        except Exception:
            logger.warning("Could not retire samples %s for user %s", to_retire, user.id, exc_info=True)
            await session.rollback()

    return {
        "has_investments": has_investments,
        "has_finances": has_expenses or has_income,
        "has_accounts": has_accounts,
        "primary_currency_set": current_settings["primary_currency"] is not None,
        "sample_investments": not has_investments and not retired["investments"],
        "sample_expenses": not has_expenses and not retired["expenses"],
        "sample_income": not has_income and not retired["income"],
        "tour_completed": current_settings["tour_completed"],
    }


# Retires a section's first-run sample for a user on explicit dismiss (the section's "Clear"). Idempotent.
async def dismiss_sample(session: AsyncSession, user: User, entity: str) -> None:
    await settings_service.retire_sample(session, user.id, entity)
    await session.commit()


# Marks the first-run welcome tour completed when the user finishes or skips it. Idempotent.
async def complete_tour(session: AsyncSession, user: User) -> None:
    await settings_service.complete_tour(session, user.id)
    await session.commit()
