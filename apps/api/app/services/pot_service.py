# Business logic for pots: the container co-ownership attaches to, its per-member permissions, and
# its value (NAV).
#
# The two governing rules from the group layer hold here unchanged, and the permission checks are
# shaped by them:
#   * ownership is a property of the record, never of the login — nothing is filtered by user_id; the
#     dual-scope RLS policies do the scoping;
#   * administration never grants visibility — a group admin manages a pot's settings and permissions
#     and gains no additional access to any member's data. `role` appears in no read path here.
#
# Visibility and write access are checked in two distinct steps, never one. `require_visible`
# answers "may you see this pot at all" and maps invisible to NotFoundError, so probing ids cannot
# distinguish a pot that is hidden from one that does not exist. `require_writable` answers "may you
# change it" and is a 403, which is safe precisely because it is only ever reached by someone who
# already passed the first check.
#
# create_pot is the one function that takes the privileged session, for the same reason create_group
# does: a pot's first permission row is exactly what app_can_view_pot reads, so the insert cannot
# satisfy its own predicate. Widening the policy with an author escape hatch would outlive the
# author's own membership, so the bootstrap runs as the owner instead.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountHasLinkedEntriesError,
    NotFoundError,
    PotHasHoldingsError,
    PotWriteRequiredError,
    ownership_percentages,
    replay_units,
    share_values,
    total_units,
    unit_price,
)
from app.models.group import GroupMember
from app.models.pot import Pot, PotMemberPermission, PotVisibility
from app.models.user import User
from app.repositories import (
    account_repository,
    card_settlement_repository,
    expense_repository,
    group_repository,
    income_repository,
    investment_repository,
    pot_ownership_repository,
    pot_repository,
    snapshot_repository,
    transfer_repository,
)
from app.schemas.pot import PotMemberShareResponse, PotPermissionResponse, PotResponse
from app.services import account_service, exchange_rate_service
from app.utils.metrics import RateLookup, convert_value

ZERO = Decimal(0)


# Whether a seat may see a pot, resolved exactly as the app_can_view_pot SQL helper does: an explicit
# permission row if there is one, otherwise the pot's visibility default. Kept in one function for the
# same reason the helper is one function — two copies of a permission rule are two things that can
# disagree, and here the second copy would disagree with the database itself.
def _may_view(pot: Pot, permission: PotMemberPermission | None) -> bool:
    if permission is not None:
        return permission.can_view
    return pot.visibility == PotVisibility.members


# Whether a seat may write to a pot. Unlike viewing, there is no visibility-style default: write is
# granted per member and nowhere else, so a pot with no permission rows is readable by its group and
# writable by nobody.
def _may_write(permission: PotMemberPermission | None) -> bool:
    return permission is not None and permission.can_write


# Resolves the caller's active seat in the pot's group plus their permission row, or raises
# NotFoundError. Used as the visibility gate: a non-member, a former member and a member without view
# permission all get the same 404 as a pot that does not exist.
async def require_visible(session: AsyncSession, pot_id: int, user: User) -> tuple[Pot, GroupMember, PotMemberPermission | None]:
    pot = await pot_repository.get_by_id(session, pot_id)
    if pot is None:
        raise NotFoundError("Pot not found")
    member = await group_repository.get_member_by_user(session, pot.group_id, user.id)
    if member is None or not member.is_active:
        raise NotFoundError("Pot not found")
    permission = await pot_repository.get_permission(session, pot.id, member.id)
    if not _may_view(pot, permission):
        raise NotFoundError("Pot not found")
    return (pot, member, permission)


# Resolves the caller's seat and requires write access to the pot. Separate from require_visible on
# purpose: "can you see it" and "can you change it" are different questions, and collapsing them is
# how a write-only rule ends up gating a read.
# Public because pot_ownership_service gates every ledger write on the same rule, and two copies of a
# permission check are two things that can disagree.
async def require_writable(session: AsyncSession, pot_id: int, user: User) -> tuple[Pot, GroupMember]:
    pot, member, permission = await require_visible(session, pot_id, user)
    if not _may_write(permission):
        raise PotWriteRequiredError()
    return (pot, member)


# The pot's value on a date, in its base currency: every holding it carries, converted at that date.
# Investments contribute their latest snapshot on or before the date; accounts contribute their
# derived balance. Both reuse the existing engines unchanged, which is the whole point of co-owning
# stock in place rather than duplicating a metrics layer for shared money.
#
# Returns None when a holding's currency cannot be converted, rather than summing the unconverted
# figure. That is the repo's standing fail-loud rule for conversion, and it matters more here than
# anywhere else: an under-stated NAV would silently misprice every unit issued against it.
async def get_nav(
    session: AsyncSession,
    pot: Pot,
    *,
    as_of_date: date_type,
    lookup: RateLookup,
) -> Decimal | None:
    rate_map = lookup.get_rate_map_at(as_of_date)
    total = ZERO

    investment_ids = await pot_repository.list_investment_ids(session, pot.id)
    if investment_ids:
        # Bounded by the date, not filtered after the fact — see the repository comment. Without the
        # bound, valuing a pot at a past date silently omits every investment snapshotted since, and
        # a back-dated ownership event would be priced against that understated NAV.
        snapshots = await snapshot_repository.get_latest_by_investments(session, investment_ids, as_of_date=as_of_date)
        for snapshot in snapshots.values():
            if snapshot.currency == pot.base_currency:
                total += snapshot.value
                continue
            if rate_map is None:
                return None
            converted = convert_value(snapshot.value, snapshot.currency, pot.base_currency, rate_map)
            if converted is None:
                return None
            total += converted

    accounts = await pot_repository.list_accounts(session, pot.id)
    if accounts:
        balances = await account_service.compute_account_balances_at(session, accounts, as_of_date=as_of_date)
        for account in accounts:
            balance = balances.get(account.id, ZERO)
            if account.currency == pot.base_currency:
                total += balance
                continue
            if rate_map is None:
                return None
            converted = convert_value(balance, account.currency, pot.base_currency, rate_map)
            if converted is None:
                return None
            total += converted

    return total


# Builds a pot response from rows the caller already loaded, so the list path can batch-load
# permissions and ledgers once for every pot instead of per row.
# `my_percentage` is deliberately derived from the same breakdown the response carries rather than
# computed separately: a headline that disagreed with the rows beneath it is worse than either
# figure being wrong on its own.
def _build_response(
    pot: Pot,
    *,
    nav: Decimal | None,
    events,
    members_by_id: dict[int, GroupMember],
    viewer_member_id: int,
    permissions: list[PotMemberPermission],
    can_write: bool,
) -> PotResponse:
    balances = replay_units([e for e in _as_entries(events)])
    percentages = ownership_percentages(balances)
    values = share_values(balances, nav) if nav is not None else {}
    outstanding = total_units(balances)
    price = unit_price(nav, outstanding) if nav is not None else None

    shares = [
        PotMemberShareResponse(
            member_id=member_id,
            display_name=members_by_id[member_id].display_name if member_id in members_by_id else "",
            units=units,
            percentage=percentages.get(member_id, ZERO),
            value=values.get(member_id),
            is_self=member_id == viewer_member_id,
        )
        for member_id, units in sorted(balances.items(), key=lambda item: (-item[1], item[0]))
    ]
    return PotResponse(
        id=pot.id,
        group_id=pot.group_id,
        name=pot.name,
        base_currency=pot.base_currency,
        visibility=pot.visibility,
        is_default=pot.is_default,
        nav=nav,
        unit_price=price,
        total_units=outstanding,
        my_percentage=next((s.percentage for s in shares if s.is_self), ZERO),
        can_write=can_write,
        shares=shares,
        permissions=[
            PotPermissionResponse(
                member_id=p.member_id,
                display_name=members_by_id[p.member_id].display_name if p.member_id in members_by_id else "",
                can_view=p.can_view,
                can_write=p.can_write,
            )
            for p in sorted(permissions, key=lambda p: p.member_id)
        ],
        created_at=pot.created_at,
        updated_at=pot.updated_at,
    )


# Turns ledger rows into the replay entries the unit math consumes, so the domain never imports a
# model and the math stays testable without a database.
def _as_entries(events):
    from app.domain import OwnershipEntry

    return [OwnershipEntry(member_id=e.member_id, units=e.units, counterparty_member_id=e.counterparty_member_id) for e in events]


# Lists every pot the caller may see, each with its ownership breakdown. Permissions, ledgers and
# rosters are batch-loaded for all pots at once, so the response cost does not grow with pot count.
# NAV is per pot because each fans out over its own holdings — see the note in get_nav.
async def list_pots(session: AsyncSession, user: User, *, group_id: int | None = None) -> list[PotResponse]:
    pots = await pot_repository.list_by_group(session, group_id) if group_id is not None else await pot_repository.list_visible(session)
    if not pots:
        return []
    pot_ids = [p.id for p in pots if p.id is not None]
    permissions_by_pot = await pot_repository.list_permissions_by_pots(session, pot_ids)
    events_by_pot = await pot_ownership_repository.list_by_pots(session, pot_ids)
    members_by_group = await group_repository.list_members_by_groups(session, sorted({p.group_id for p in pots}))
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    today = date_type.today()

    responses = []
    for pot in pots:
        members = members_by_group.get(pot.group_id, [])
        viewer = next((m for m in members if m.user_id == user.id and m.is_active), None)
        # RLS returns only pots the user may see, so a missing viewer seat means the policy and this
        # service disagree. Skip rather than raise: under-reporting is the fail-closed direction, and
        # a 500 on a list page would hide every other pot the user legitimately owns.
        if viewer is None:
            continue
        permissions = permissions_by_pot.get(pot.id, [])
        mine = next((p for p in permissions if p.member_id == viewer.id), None)
        nav = await get_nav(session, pot, as_of_date=today, lookup=lookup)
        responses.append(
            _build_response(
                pot,
                nav=nav,
                events=events_by_pot.get(pot.id, []),
                members_by_id={m.id: m for m in members},
                viewer_member_id=viewer.id,
                permissions=permissions,
                can_write=_may_write(mine),
            )
        )
    return responses


# Fetches one pot with its ownership breakdown. Raises NotFoundError when it does not exist or the
# caller may not see it — the same answer for both.
async def get_pot(session: AsyncSession, pot_id: int, user: User, *, as_of_date: date_type | None = None) -> PotResponse:
    pot, viewer, permission = await require_visible(session, pot_id, user)
    members = await group_repository.list_members(session, pot.group_id)
    permissions = await pot_repository.list_permissions(session, pot.id)
    events = await pot_ownership_repository.list_by_pot(session, pot.id, as_of_date=as_of_date)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    nav = await get_nav(session, pot, as_of_date=as_of_date or date_type.today(), lookup=lookup)
    return _build_response(
        pot,
        nav=nav,
        events=events,
        members_by_id={m.id: m for m in members},
        viewer_member_id=viewer.id,
        permissions=permissions,
        can_write=_may_write(permission),
    )


# Creates a pot and seats its creator with full access, in one transaction. Runs on the PRIVILEGED
# session — see the module comment: the permission row this needs is the one the RLS policy reads.
# The creator always gets an explicit row rather than relying on the visibility default, because a
# pot created with visibility='owners' would otherwise be immediately invisible to everyone including
# the person who just made it, and there would be no one left able to grant access.
async def create_pot(
    admin_session: AsyncSession,
    group_id: int,
    user: User,
    *,
    base_currency: str,
    name: str | None = None,
    visibility: PotVisibility = PotVisibility.members,
) -> PotResponse:
    from app.services import group_service

    group, member = await group_service.require_admin(admin_session, group_id, user)
    existing = await pot_repository.list_by_group(admin_session, group.id)
    pot = Pot(
        group_id=group.id,
        name=name,
        base_currency=base_currency,
        visibility=visibility,
        # The first pot in a group is its default and needs no name; a second one always does.
        is_default=not existing,
    )
    pot = await pot_repository.create(admin_session, pot)
    await pot_repository.save_permission(admin_session, PotMemberPermission(pot_id=pot.id, member_id=member.id, can_view=True, can_write=True))
    await admin_session.commit()
    return await get_pot(admin_session, pot.id, user)


# Renames a pot, changes its base currency or its visibility. Only provided fields are updated.
# Group admin only — this is configuration, not money movement, so it follows the membership rules
# rather than the pot's own write permission.
async def update_pot(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    name: str | None = None,
    visibility: PotVisibility | None = None,
) -> PotResponse:
    from app.services import group_service

    pot, _, _ = await require_visible(session, pot_id, user)
    await group_service.require_admin(session, pot.group_id, user)
    if name is not None:
        pot.name = name
    if visibility is not None:
        pot.visibility = visibility
    await pot_repository.save(session, pot)
    await session.commit()
    await session.refresh(pot)
    return await get_pot(session, pot.id, user)


# Deletes a pot. Refused while it still holds anything: the database refuses it too (every pot_id
# foreign key is ON DELETE RESTRICT), and this turns that into a real message rather than an
# integrity error. Group admin only.
async def delete_pot(session: AsyncSession, pot_id: int, user: User) -> None:
    from app.services import group_service

    pot, _, _ = await require_visible(session, pot_id, user)
    await group_service.require_admin(session, pot.group_id, user)
    holdings = await pot_repository.count_holdings(session, pot.id)
    if holdings:
        raise PotHasHoldingsError(holdings)
    await pot_repository.delete(session, pot)
    await session.commit()


# Grants or changes one member's access to a pot. Group admin only, per V4/V6 — and note that being
# an admin is what lets you SET this, never what lets you read anything: an admin with can_view false
# sees nothing of the pot, which is the whole content of "administration never grants visibility".
async def set_permission(
    session: AsyncSession,
    pot_id: int,
    member_id: int,
    user: User,
    *,
    can_view: bool,
    can_write: bool,
) -> PotResponse:
    from app.services import group_service

    pot, _, _ = await require_visible(session, pot_id, user)
    await group_service.require_admin(session, pot.group_id, user)
    member = await group_repository.get_member(session, pot.group_id, member_id)
    if member is None:
        raise NotFoundError("Group member not found")
    await pot_repository.save_permission(
        session,
        # can_write implies can_view, enforced by a CHECK on the table as well: writing something you
        # cannot see is not a state this product has a meaning for.
        PotMemberPermission(pot_id=pot.id, member_id=member.id, can_view=can_view or can_write, can_write=can_write),
    )
    await session.commit()
    return await get_pot(session, pot.id, user)


# Removes a member's explicit permission row, dropping them back to the pot's visibility default.
# Group admin only.
async def clear_permission(session: AsyncSession, pot_id: int, member_id: int, user: User) -> PotResponse:
    from app.services import group_service

    pot, _, _ = await require_visible(session, pot_id, user)
    await group_service.require_admin(session, pot.group_id, user)
    permission = await pot_repository.get_permission(session, pot.id, member_id)
    if permission is None:
        raise NotFoundError("Pot permission not found")
    await pot_repository.delete_permission(session, permission)
    await session.commit()
    return await get_pot(session, pot.id, user)


# Moves holdings into a pot, or back out of it into the caller's private scope.
#
# Two guards, and neither is optional:
#
#   * Moving IN requires the holding to be the caller's own private one. Without that, naming
#     someone else's id would co-opt their money into a pot they never agreed to share.
#
#   * An ACCOUNT with linked entries cannot move in at all. Its balance derives from expenses,
#     income, settlements and transfers that are owned by ONE user, so a shared account carrying them
#     would report a different balance to every member depending on whose rows they can see — a
#     figure that changes with the reader is worse than one that is merely wrong. A transfer is the
#     sharpest case: it would end up with one leg in each scope, which §4.1 forbids outright.
#     The remedy is a fresh account, which is also what U5 means by scope being fixed at creation.
#
# Investments need no such guard: their snapshots and transactions belong to the investment rather
# than to a user, so they move with it and the repository re-points them in the same statement set.
async def move_holdings(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    investment_ids: list[int] | None = None,
    account_ids: list[int] | None = None,
    into: bool = True,
) -> PotResponse:
    pot, member = await require_writable(session, pot_id, user)
    investment_ids = investment_ids or []
    account_ids = account_ids or []

    if investment_ids:
        found = await investment_repository.get_by_ids_any_scope(session, investment_ids)
        _ensure_all_present(found, investment_ids, pot, user, into=into)
    if account_ids:
        accounts = await account_repository.get_by_ids_any_scope(session, account_ids)
        _ensure_all_present(accounts, account_ids, pot, user, into=into)
        await _ensure_account_carries_no_movements(session, account_ids, user)

    await investment_repository.move_to_scope(session, investment_ids, pot_id=pot.id if into else None, user_id=None if into else user.id)
    await account_repository.move_to_scope(session, account_ids, pot_id=pot.id if into else None, user_id=None if into else user.id)
    await session.commit()
    return await get_pot(session, pot.id, user)


# Refuses to move an account across the scope boundary while anything references it.
#
# Applied in BOTH directions, which is the correction: guarding only the way in leaves the way out
# open, and the way out is where the damage is worse. An account's balance derives from expenses,
# income, settlements and transfers, so a shared one carrying rows owned by one person would report a
# different figure to every member depending on whose rows they can see — a figure that changes with
# the reader is worse than one that is merely wrong. Leaving a pot is the mirror image: a transfer
# between two pot accounts would end up with one leg in each scope, which no transfer may have, and
# the balance union would silently stop counting it.
#
# Three checks, because none of them sees what the others do:
#   * linked_account_ids across the four movement tables — filtered by user_id, so it sees a PRIVATE
#     account's history and is the right question on the way in;
#   * transfer_repository.exists_for_accounts — scope-FREE, because the user_id filter above is
#     structurally blind to a pot-scoped transfer, which is exactly the row that matters on the way
#     out;
#   * pot_ownership_repository.exists_for_accounts — an ownership event names a private account on
#     one leg and a pot account on the other, so moving either would put both ends in one scope:
#     money that left the pot and arrived back in it.
async def _ensure_account_carries_no_movements(session: AsyncSession, account_ids: list[int], user: User) -> None:
    linked = (
        await income_repository.linked_account_ids(session, account_ids, user.id)
        | await expense_repository.linked_account_ids(session, account_ids, user.id)
        | await card_settlement_repository.linked_account_ids(session, account_ids, user.id)
        | await transfer_repository.linked_account_ids(session, account_ids, user.id)
    )
    if not linked and await transfer_repository.exists_for_accounts(session, account_ids):
        linked = set(account_ids)
    if not linked and await pot_ownership_repository.exists_for_accounts(session, account_ids):
        linked = set(account_ids)
    if linked:
        raise AccountHasLinkedEntriesError(sorted(linked))


# Refuses the whole move when any named holding is missing, rather than moving the ones that were
# found. A partial move is the worst outcome available here: the caller is told nothing failed while
# some of what they named stayed where it was.
# `into=False` additionally requires each holding to already belong to THIS pot, so an id from
# another pot cannot be pulled into the caller's private scope by guessing.
def _ensure_all_present(found: list, requested: list[int], pot: Pot, user: User, *, into: bool) -> None:
    if into:
        # The owner check is belt-and-braces over RLS, which already returns a private row only to its
        # owner — but this is the one place where getting it wrong co-opts someone else's money, so it
        # is stated rather than inherited.
        eligible = {h.id for h in found if h.pot_id is None and h.user_id == user.id}
    else:
        eligible = {h.id for h in found if h.pot_id == pot.id}
    if set(requested) - eligible:
        raise NotFoundError("Holding not found")


# Re-points every holding in a group's pots to one user as private. Called only from account deletion,
# when the leaving account holds the group's last active linked seat: at that moment the placeholders
# have no way to ever see the money again, so the honest reading is that it was always this user's.
# Runs BEFORE the account row goes, for the same ordering reason the orphan-group read does — and it
# has to, because afterwards there is no user id left to assign.
async def absorb_group_pots(session: AsyncSession, group_ids: list[int], user_id: int) -> int:
    if not group_ids:
        return 0
    moved = 0
    for group_id in group_ids:
        for pot in await pot_repository.list_by_group(session, group_id):
            moved += await investment_repository.reassign_pot_to_user(session, pot.id, user_id)
            moved += await account_repository.reassign_pot_to_user(session, pot.id, user_id)
    return moved
