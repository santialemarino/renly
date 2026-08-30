# Data access for a group's shared money settings. Scoped by the membership RLS policy like every other
# group table, so no query here carries a user filter.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.group_money_settings import GroupMoneySettings


# The settings rows for the given groups, keyed by group id. The batch form is the only form: every
# caller reads a list of groups, and a per-group lookup inside that loop is the N+1 this avoids.
async def get_by_group_ids(session: AsyncSession, group_ids: list[int]) -> dict[int, GroupMoneySettings]:
    if not group_ids:
        return {}
    result = await session.execute(select(GroupMoneySettings).where(GroupMoneySettings.group_id.in_(group_ids)))
    return {settings.group_id: settings for settings in result.scalars().all()}


# One group's settings row, or None when the group is invisible to the caller.
async def get_by_group_id(session: AsyncSession, group_id: int) -> GroupMoneySettings | None:
    result = await session.execute(select(GroupMoneySettings).where(GroupMoneySettings.group_id == group_id))
    return result.scalar_one_or_none()


# Inserts the settings row that every group gets when it is created.
async def create(session: AsyncSession, settings: GroupMoneySettings) -> GroupMoneySettings:
    session.add(settings)
    await session.flush()
    return settings


# Stages the settings for update (caller commits).
async def save(session: AsyncSession, settings: GroupMoneySettings) -> None:
    session.add(settings)


# Namespace to call repository functions (e.g. group_money_settings_repository.get_by_group_id).
class GroupMoneySettingsRepository:
    create = staticmethod(create)
    get_by_group_id = staticmethod(get_by_group_id)
    get_by_group_ids = staticmethod(get_by_group_ids)
    save = staticmethod(save)


# Singleton used by services to access group money settings.
group_money_settings_repository = GroupMoneySettingsRepository()
