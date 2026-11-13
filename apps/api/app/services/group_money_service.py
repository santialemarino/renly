# Business logic for the money settings a group holds in common.
#
# A sibling of group_service rather than part of it, mirroring the schema: `groups` carries who the
# people are and nothing about what they share, so the money settings live in their own table and
# their own service. That is what lets the membership kernel stay adoptable by a non-money module.
#
# Reading is any member's; changing the split default and auto-finalise is the admin's. Setting the
# standard a group holds itself to is management, not money movement — the same split every other group
# setting follows. The DOLLAR RATE is the exception, and deliberately: it decides how much of one
# currency's debt a payment in another clears, so it moves money between members, and changing it takes
# every active member's agreement (see the section below).

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    GroupDollarRateAlreadyAgreedError,
    GroupDollarRateNotYoursError,
    GroupDollarRateProposalPendingError,
    GroupDollarRateUnchangedError,
    NotFoundError,
    dollar_rate_consent,
)
from app.models.exchange_rate import DollarRate
from app.models.group import GroupMember
from app.models.group_money_settings import GroupMoneySettings, SplitMethod
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User
from app.repositories import group_money_settings_repository, group_repository
from app.schemas.group_settlement import GroupDollarRateProposalResponse, GroupMoneySettingsResponse
from app.services import group_service, shared_audit_service

# How an audit entry names each step of a dollar-rate change — the same variants a pot's use, so the
# activity feed phrases both alike. Translation keys on the other side.
_RATE_PROPOSED = "dollar_rate_proposed"
_RATE_WITHDRAWN = "dollar_rate_withdrawn"
_RATE_APPLIED = "dollar_rate"


# The group's money settings. Every group has a row — created with the group and backfilled for the
# ones that predate it — so a missing one is a broken invariant rather than a defaulting case, and it
# answers 404 instead of quietly inventing settings nobody chose.
async def get_settings(session: AsyncSession, group_id: int, user: User) -> GroupMoneySettingsResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    settings = await _require_settings(session, group_id)
    return await _settings_response(session, settings, viewer)


# Updates the group's split default and auto-finalise. Only provided fields change. Admin only.
async def update_settings(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    default_split_method: SplitMethod | None = None,
    auto_finalise_settlements: bool | None = None,
) -> GroupMoneySettingsResponse:
    _, viewer = await group_service.require_admin(session, group_id, user)
    settings = await _require_settings(session, group_id)
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
    return await _settings_response(session, settings, viewer)


# Creates the settings row that every group gets, at the dollar rate its creator chose. Called from
# group creation on the PRIVILEGED session, for the same reason the group's first membership row is
# written there: the membership RLS policy this table shares reads a row that does not exist yet.
async def seed_settings(session: AsyncSession, group_id: int, *, dollar_rate: DollarRate = DollarRate.mep) -> GroupMoneySettings:
    return await group_money_settings_repository.create(session, GroupMoneySettings(group_id=group_id, dollar_rate=dollar_rate))


# --- The dollar rate, changed by the members' agreement ---
#
# The group settles up at ONE dollar rate: it prices a payment in one currency against debt in another,
# and the "at today's rate" figure beside a balance. Both sides of a debt must stand behind those, so the
# rate is the group's rather than each member's — and since a change of it moves what every member's
# payments clear, it changes the way a pot's rate does: one member proposes, every other active member
# agrees, nothing changes until all of them have, and the proposer may withdraw it meanwhile. With one
# active member there is nobody to wait for, and it applies at once. The rule itself lives in
# app.domain.dollar_rate_consent, shared with pots; only who the parties are is stated here.
#
# Recorded settlements are never recomputed: each stores the amounts it cleared. A new rate reaches
# future payments and the live balance figure only.
#
# Who the members are is asked of the roster every time, never stored with the proposal, so a member
# who leaves or joins while one waits is counted as the group stands when it would apply.
# `settle_dollar_rate_proposal` is what applies a proposal once its last holdout leaves.


# The seats a dollar-rate change waits for: every active seat with an account behind it.
#
# A name-only seat, or one that has left, can never answer, so it is not waited for — the posture a pot
# takes towards its owners, and for the same reason: waiting on a seat that cannot act would freeze the
# group's rate for good.
def _rate_agreers(members_by_id: dict[int, GroupMember]) -> set[int]:
    return {member.id for member in members_by_id.values() if member.is_active and member.user_id is not None}


# Whether the proposer of the pending change can still act on it: an active seat with an account.
def _proposer_can_act(settings: GroupMoneySettings, members_by_id: dict[int, GroupMember]) -> bool:
    proposer = members_by_id.get(settings.dollar_rate_proposed_by)
    return proposer is not None and proposer.is_active and proposer.user_id is not None


# The settings as the reader sees them, the pending proposal resolved from the same _rate_agreers the
# writes ask, so a button offered is an act accepted.
async def _settings_response(session: AsyncSession, settings: GroupMoneySettings, viewer: GroupMember) -> GroupMoneySettingsResponse:
    proposal = None
    if settings.dollar_rate_proposal is not None:
        members_by_id = {member.id: member for member in await group_repository.list_members(session, settings.group_id)}
        agreers = _rate_agreers(members_by_id)
        agreed = set(settings.dollar_rate_agreed_by)
        proposer = members_by_id.get(settings.dollar_rate_proposed_by)
        proposal = GroupDollarRateProposalResponse(
            dollar_rate=settings.dollar_rate_proposal,
            proposed_by=proposer.display_name if proposer is not None else "",
            waiting_on=sorted(members_by_id[member_id].display_name for member_id in dollar_rate_consent.waiting_on(agreers, agreed)),
            can_agree=dollar_rate_consent.may_agree(viewer.id, agreers, agreed),
            can_withdraw=dollar_rate_consent.may_withdraw(
                viewer.id, settings.dollar_rate_proposed_by, agreers, proposer_can_act=_proposer_can_act(settings, members_by_id)
            ),
        )
    return GroupMoneySettingsResponse(
        group_id=settings.group_id,
        default_split_method=settings.default_split_method,
        auto_finalise_settlements=settings.auto_finalise_settlements,
        dollar_rate=settings.dollar_rate,
        dollar_rate_proposal=proposal,
        can_change_dollar_rate=settings.dollar_rate_proposal is None,
    )


# Proposes a new dollar rate, or sets it outright when the caller is the group's only active member.
#
# Any active member may propose: each of them settles at it. The group row is locked first, so two
# proposals cannot both find nothing pending, and the roster is read under the lock.
async def propose_dollar_rate(session: AsyncSession, group_id: int, user: User, *, dollar_rate: DollarRate) -> GroupMoneySettingsResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    await group_repository.lock(session, group_id)
    settings = await _require_settings(session, group_id)
    if settings.dollar_rate_proposal is not None:
        raise GroupDollarRateProposalPendingError()
    if dollar_rate == settings.dollar_rate:
        raise GroupDollarRateUnchangedError()
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    if _rate_agreers(members_by_id) <= {viewer.id}:
        await _apply_dollar_rate(session, settings, user, rate=dollar_rate)
    else:
        settings.dollar_rate_proposal = dollar_rate
        settings.dollar_rate_proposed_by = viewer.id
        settings.dollar_rate_agreed_by = [viewer.id]
        await group_money_settings_repository.save(session, settings)
        await _audit(session, group_id, user, AuditAction.updated, variant=_RATE_PROPOSED, from_rate=settings.dollar_rate, to_rate=dollar_rate)
    await session.commit()
    await session.refresh(settings)
    return await _settings_response(session, settings, viewer)


# Gives the caller's agreement to the pending change, and applies it once every active member has.
#
# A member who already agreed may still call this when nobody is left to wait for — the backstop for a
# proposal whose last holdout went away without settle_dollar_rate_proposal applying it.
async def agree_dollar_rate(session: AsyncSession, group_id: int, user: User) -> GroupMoneySettingsResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    await group_repository.lock(session, group_id)
    settings = await _require_settings(session, group_id)
    if settings.dollar_rate_proposal is None:
        raise NotFoundError("Dollar rate proposal not found")
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    agreers = _rate_agreers(members_by_id)
    agreed = set(settings.dollar_rate_agreed_by)
    if not dollar_rate_consent.may_agree(viewer.id, agreers, agreed):
        raise GroupDollarRateAlreadyAgreedError()
    if viewer.id not in agreed:
        settings.dollar_rate_agreed_by = [*settings.dollar_rate_agreed_by, viewer.id]
        agreed.add(viewer.id)
        await _audit(session, group_id, user, AuditAction.confirmed, from_rate=settings.dollar_rate, to_rate=settings.dollar_rate_proposal)
    if dollar_rate_consent.is_agreed(agreers, agreed):
        await _apply_dollar_rate(session, settings, user, rate=settings.dollar_rate_proposal)
    else:
        await group_money_settings_repository.save(session, settings)
    await session.commit()
    await session.refresh(settings)
    return await _settings_response(session, settings, viewer)


# Withdraws the pending change. Nothing had changed, so nothing is undone.
async def withdraw_dollar_rate(session: AsyncSession, group_id: int, user: User) -> GroupMoneySettingsResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    await group_repository.lock(session, group_id)
    settings = await _require_settings(session, group_id)
    if settings.dollar_rate_proposal is None:
        raise NotFoundError("Dollar rate proposal not found")
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    if not dollar_rate_consent.may_withdraw(
        viewer.id, settings.dollar_rate_proposed_by, _rate_agreers(members_by_id), proposer_can_act=_proposer_can_act(settings, members_by_id)
    ):
        raise GroupDollarRateNotYoursError()
    proposed = settings.dollar_rate_proposal
    _clear_rate_proposal(settings)
    await group_money_settings_repository.save(session, settings)
    await _audit(session, group_id, user, AuditAction.updated, variant=_RATE_WITHDRAWN, from_rate=settings.dollar_rate, to_rate=proposed)
    await session.commit()
    await session.refresh(settings)
    return await _settings_response(session, settings, viewer)


# Applies a pending proposal when the roster no longer leaves anybody to wait for. Called by every path
# that takes a seat out of the agreement — a member removed or leaving, an account deleted — on the
# caller's session and inside the caller's transaction; the caller commits.
#
# `leaving` names seats about to stop counting that the roster still shows as active. Removing a member
# settles BEFORE the seat goes inactive, because a member who leaves loses the membership the settings
# row's policy (and the audit entry's) asks of the writer the moment their seat goes — the same
# ordering rule the removal's own audit entry follows.
#
# A seat JOINING needs nothing here: agreers are read from the roster on every act, so a member who
# joins while a proposal waits is simply waited for too.
async def settle_dollar_rate_proposal(session: AsyncSession, group_id: int, actor: User | None, *, leaving: frozenset[int] = frozenset()) -> None:
    settings = await group_money_settings_repository.get_by_group_id(session, group_id)
    if settings is None or settings.dollar_rate_proposal is None:
        return
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    if dollar_rate_consent.is_agreed(_rate_agreers(members_by_id) - leaving, set(settings.dollar_rate_agreed_by)):
        await _apply_dollar_rate(session, settings, actor, rate=settings.dollar_rate_proposal)


# --- Internal ---


# The group's settings row, or 404. See get_settings for why a missing one is not defaulted.
async def _require_settings(session: AsyncSession, group_id: int) -> GroupMoneySettings:
    settings = await group_money_settings_repository.get_by_group_id(session, group_id)
    if settings is None:
        raise NotFoundError("Group not found")
    return settings


# Applies a new dollar rate: records the change from the old rate to the new one and clears any
# proposal. FUTURE figures only — every recorded settlement keeps the amounts it was written with. The
# caller commits.
async def _apply_dollar_rate(session: AsyncSession, settings: GroupMoneySettings, actor: User | None, *, rate: DollarRate) -> None:
    previous = settings.dollar_rate
    settings.dollar_rate = rate
    _clear_rate_proposal(settings)
    await group_money_settings_repository.save(session, settings)
    await _audit(session, settings.group_id, actor, AuditAction.updated, variant=_RATE_APPLIED, from_rate=previous, to_rate=rate)


# Forgets the pending proposal, whole: the CHECK on the table refuses a rate without its proposer.
def _clear_rate_proposal(settings: GroupMoneySettings) -> None:
    settings.dollar_rate_proposal = None
    settings.dollar_rate_proposed_by = None
    settings.dollar_rate_agreed_by = []


# Records one step of a dollar-rate change in the group's activity: the rate it was and the rate it
# would be, as stored values the feed names in the reader's language.
async def _audit(
    session: AsyncSession,
    group_id: int,
    actor: User | None,
    action: AuditAction,
    *,
    from_rate: DollarRate,
    to_rate: DollarRate,
    variant: str | None = None,
) -> None:
    payload = {"from_rate": from_rate.value, "to_rate": to_rate.value}
    if variant is not None:
        payload["variant"] = variant
    await shared_audit_service.record(
        session,
        group_id=group_id,
        actor=actor,
        entity_type=AuditEntityType.group_money_settings,
        action=action,
        payload=payload,
    )
