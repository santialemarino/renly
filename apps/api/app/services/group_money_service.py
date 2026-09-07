# Business logic for the money settings a group holds in common.
#
# A sibling of group_service rather than part of it, mirroring the schema: `groups` carries who the
# people are and nothing about what they share, so the money settings live in their own table and
# their own service. That is what lets the membership kernel stay adoptable by a non-money module.
#
# Reading is any member's; changing is the admin's. Setting the standard a group holds itself to is
# management, not money movement — the same split every other group setting follows.

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.group_money_settings import GroupMoneySettings, SplitMethod
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User
from app.repositories import group_money_settings_repository
from app.schemas.group_settlement import GroupMoneySettingsResponse
from app.services import group_service, shared_audit_service


# The group's money settings. Every group has a row — created with the group and backfilled for the
# ones that predate it — so a missing one is a broken invariant rather than a defaulting case, and it
# answers 404 instead of quietly inventing settings nobody chose.
async def get_settings(session: AsyncSession, group_id: int, user: User) -> GroupMoneySettingsResponse:
    await group_service.require_member(session, group_id, user)
    settings = await group_money_settings_repository.get_by_group_id(session, group_id)
    if settings is None:
        raise NotFoundError("Group not found")
    return GroupMoneySettingsResponse.model_validate(settings)


# Updates the group's money settings. Only provided fields change. Admin only.
async def update_settings(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    default_split_method: SplitMethod | None = None,
    auto_finalise_settlements: bool | None = None,
) -> GroupMoneySettingsResponse:
    await group_service.require_admin(session, group_id, user)
    settings = await group_money_settings_repository.get_by_group_id(session, group_id)
    if settings is None:
        raise NotFoundError("Group not found")
    if default_split_method is not None:
        settings.default_split_method = default_split_method
    if auto_finalise_settlements is not None:
        settings.auto_finalise_settlements = auto_finalise_settlements
    await group_money_settings_repository.save(session, settings)
    await shared_audit_service.record(
        session,
        group_id=group_id,
        actor=user,
        entity_type=AuditEntityType.group_money_settings,
        action=AuditAction.updated,
        # No entity_id: the settings are keyed BY the group, so the id would restate group_id. And no
        # values: naming the new split method would need a second vocabulary of their labels in both
        # locales, where the settings dialog already states them.
    )
    await session.commit()
    await session.refresh(settings)
    return GroupMoneySettingsResponse.model_validate(settings)


# Creates the settings row that every group gets. Called from group creation on the PRIVILEGED session,
# for the same reason the group's first membership row is written there: the membership RLS policy this
# table shares reads a row that does not exist yet.
async def seed_settings(session: AsyncSession, group_id: int) -> GroupMoneySettings:
    return await group_money_settings_repository.create(session, GroupMoneySettings(group_id=group_id))
