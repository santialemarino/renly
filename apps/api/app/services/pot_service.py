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
    PotAlreadyDividedError,
    PotHasHoldingsError,
    PotValuation,
    PotWriteRequiredError,
    is_valuation_overdue,
    ownership_percentages,
    period_ends,
    replay_units,
    series_interval,
    share_values,
    total_units,
    unit_price,
)
from app.models.account import Account
from app.models.group import GroupMember
from app.models.investment import Investment
from app.models.pot import Pot, PotCadence, PotMemberPermission, PotVisibility
from app.models.snapshot import InvestmentSnapshot
from app.models.user import User
from app.repositories import (
    account_repository,
    card_settlement_repository,
    expense_repository,
    group_repository,
    group_settlement_repository,
    income_repository,
    investment_repository,
    pot_ownership_repository,
    pot_repository,
    shared_expense_repository,
    shared_income_repository,
    snapshot_repository,
    transfer_repository,
)
from app.schemas.pot import (
    PotHoldingResponse,
    PotHoldingsResponse,
    PotMemberShareResponse,
    PotPermissionResponse,
    PotResponse,
    PotValueSeriesPoint,
    PotValueSeriesResponse,
)
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


# One figure restated in the pot's base currency, or None when it cannot be stated there at all.
#
# One function because the NAV sum and the holdings read must agree about what a holding is worth;
# what they do with a None is where they deliberately differ. The NAV abandons the whole sum (an
# under-stated NAV would misprice every unit issued against it), while the holdings read leaves that
# one row's base figure unknown and still lists the holding.
def _to_base_currency(value: Decimal, currency: str, base_currency: str, rate_map) -> Decimal | None:
    if currency == base_currency:
        return value
    if rate_map is None:
        return None
    return convert_value(value, currency, base_currency, rate_map)


# Adds a set of holdings' figures to a running total in the pot's base currency, or answers None the
# moment the total stops being statable in full. A `None` figure is a holding nobody has valued.
#
# THE one place the NAV's refusal rule lives, shared by the point-in-time valuation and the value
# series — because a series whose points were computed by a second copy of this rule is a second
# algorithm that has to agree with the first at every date, and the shape to watch for (§18) is
# exactly a sum that drops a term instead of refusing.
def _add_holdings(total: Decimal, figures: list[tuple[Decimal, str] | None], base_currency: str, rate_map) -> Decimal | None:
    for figure in figures:
        if figure is None:
            return None
        converted = _to_base_currency(figure[0], figure[1], base_currency, rate_map)
        if converted is None:
            return None
        total += converted
    return total


# The pot's value on a date, in its base currency: every holding it carries, converted at that date.
# Investments contribute their latest snapshot on or before the date; accounts contribute their
# derived balance. Both reuse the existing engines unchanged, which is the whole point of co-owning
# stock in place rather than duplicating a metrics layer for shared money.
#
# Returns (nav, valued_as_of, holds_anything). The NAV is None — never a partial total — in every case
# where the figure cannot be stated in full:
#
#   * a holding whose currency cannot be converted. The repo's standing fail-loud rule.
#   * a holding with no valuation at all (an investment nobody has snapshotted on or before the date).
#     Omitting it would report a complete-looking figure for an incomplete pot, and the harm is not
#     cosmetic: a contribution priced against it issues units against a value that is not the pot's,
#     which moves real value between owners. Same failure as bounding the snapshot query wrongly,
#     reached from the other direction.
#   * nothing to value at all. A NAV is a valuation OF something, and an empty sum is not "worth
#     nothing" — a pot cannot be valued at <= 0 for ownership purposes anyway (spec 5.4), so zero was
#     never a usable answer. Null is also what PotResponse documents for a pot with no holdings.
#
# An ARCHIVED holding is not counted by either query and so cannot make the NAV unknown: it
# contributes nothing to the pot's value by design, which is a different thing from being unvalued.
async def _value_pot(
    session: AsyncSession,
    pot: Pot,
    *,
    as_of_date: date_type,
    lookup: RateLookup,
) -> tuple[Decimal | None, date_type | None, bool]:
    rate_map = lookup.get_rate_map_at(as_of_date)

    investment_ids = await pot_repository.list_investment_ids(session, pot.id)
    valued_as_of: date_type | None = None
    total: Decimal | None = ZERO
    if investment_ids:
        # Bounded by the date, not filtered after the fact — see the repository comment. Without the
        # bound, valuing a pot at a past date silently omits every investment snapshotted since, and
        # a back-dated ownership event would be priced against that understated NAV.
        snapshots = await snapshot_repository.get_latest_by_investments(session, investment_ids, as_of_date=as_of_date)
        # The OLDEST of the latest snapshots, because the pot's value is only as current as its
        # stalest term — one holding nobody has touched since March makes the whole figure a March
        # figure, however fresh the rest are. None when any holding has no snapshot at all.
        found = [snapshots[investment_id].date for investment_id in investment_ids if investment_id in snapshots]
        valued_as_of = min(found) if len(found) == len(investment_ids) else None
        figures = [
            None if investment_id not in snapshots else (snapshots[investment_id].value, snapshots[investment_id].currency)
            for investment_id in investment_ids
        ]
        total = _add_holdings(total, figures, pot.base_currency, rate_map)
        # Returned here so the two lookups keep their original order and neither runs when the other
        # has already answered None — an unconvertible investment must not cost a balance query.
        if total is None:
            return (None, valued_as_of, True)

    accounts = await pot_repository.list_accounts(session, pot.id)
    if accounts:
        # An account's balance is DERIVED at the date asked about, so it is current by construction
        # and never pulls valued_as_of backwards; only a snapshot can. A pot holding accounts alone is
        # therefore known as of the date itself.
        if not investment_ids:
            valued_as_of = as_of_date
        # No missing case here either: an account always has a balance — its opening figure at worst.
        balances = await account_service.compute_account_balances_at(session, accounts, as_of_date=as_of_date)
        total = _add_holdings(total, [(balances.get(a.id, ZERO), a.currency) for a in accounts], pot.base_currency, rate_map)
        if total is None:
            return (None, valued_as_of, True)

    if not investment_ids and not accounts:
        return (None, None, False)
    return (total, valued_as_of, True)


# The pot's value on a date plus how current that value is: see PotValuation for what each null means.
#
# Freshness is measured against `as_of_date` rather than against the wall clock, so a pot valued at a
# past date answers "was it up to date then" instead of mixing two frames in one response. Every
# surface that shows freshness asks about today, which is the parameter's default at every caller.
async def get_valuation(
    session: AsyncSession,
    pot: Pot,
    *,
    as_of_date: date_type,
    lookup: RateLookup,
) -> PotValuation:
    nav, valued_as_of, holds_anything = await _value_pot(session, pot, as_of_date=as_of_date, lookup=lookup)
    return PotValuation(
        nav=nav,
        valued_as_of=valued_as_of,
        is_stale=is_valuation_overdue(
            cadence=pot.snapshot_cadence,
            valued_as_of=valued_as_of,
            holds_anything=holds_anything,
            today=as_of_date,
        ),
    )


# The pot's value on a date, for a caller that needs only the figure — the ownership ledger prices
# every movement against it. A thin read over get_valuation so there is one valuation engine.
async def get_nav(
    session: AsyncSession,
    pot: Pot,
    *,
    as_of_date: date_type,
    lookup: RateLookup,
) -> Decimal | None:
    return (await get_valuation(session, pot, as_of_date=as_of_date, lookup=lookup)).nav


# Builds a pot response from rows the caller already loaded, so the list path can batch-load
# permissions and ledgers once for every pot instead of per row.
# `my_percentage` is deliberately derived from the same breakdown the response carries rather than
# computed separately: a headline that disagreed with the rows beneath it is worse than either
# figure being wrong on its own.
def _build_response(
    pot: Pot,
    *,
    valuation: PotValuation,
    events,
    members_by_id: dict[int, GroupMember],
    viewer_member_id: int,
    permissions: list[PotMemberPermission],
    can_write: bool,
) -> PotResponse:
    nav = valuation.nav
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
        snapshot_cadence=pot.snapshot_cadence,
        visibility=pot.visibility,
        is_default=pot.is_default,
        nav=nav,
        valued_as_of=valuation.valued_as_of,
        is_stale=valuation.is_stale,
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
        valuation = await get_valuation(session, pot, as_of_date=today, lookup=lookup)
        responses.append(
            _build_response(
                pot,
                valuation=valuation,
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
    valuation = await get_valuation(session, pot, as_of_date=as_of_date or date_type.today(), lookup=lookup)
    return _build_response(
        pot,
        valuation=valuation,
        events=events,
        members_by_id={m.id: m for m in members},
        viewer_member_id=viewer.id,
        permissions=permissions,
        can_write=_may_write(permission),
    )


# One holding's response row: its own figure, plus that figure restated in the pot's base currency.
# `value is None` means nobody has valued it yet, so there is nothing to restate either — null both
# ways rather than a zero that would read as "worth nothing".
def _holding_response(
    holding_id: int,
    name: str,
    currency: str,
    value: Decimal | None,
    is_active: bool,
    *,
    pot: Pot,
    rate_map,
    valued_on: date_type | None,
) -> PotHoldingResponse:
    return PotHoldingResponse(
        id=holding_id,
        name=name,
        currency=currency,
        value=value,
        base_value=None if value is None else _to_base_currency(value, currency, pot.base_currency, rate_map),
        is_active=is_active,
        valued_on=valued_on,
    )


# One investment's row, valued at its latest snapshot on or before today.
# The figure is read in the SNAPSHOT's currency, not the investment's `base_currency`: the NAV
# converts from that same column, and the two must not be able to disagree about which currency a
# figure is in. They are enforced equal on write, which is not the same as being one column. With no
# snapshot there is no value to state at all, and the investment's own currency says which currency it
# would have been in.
def _investment_holding(investment: Investment, snapshot: InvestmentSnapshot | None, *, pot: Pot, rate_map) -> PotHoldingResponse:
    currency = investment.base_currency if snapshot is None else snapshot.currency
    value = None if snapshot is None else snapshot.value
    return _holding_response(
        investment.id,
        investment.name,
        currency,
        value,
        investment.is_active,
        pot=pot,
        rate_map=rate_map,
        valued_on=None if snapshot is None else snapshot.date,
    )


# One account's row, valued at its derived balance today. An account always has a balance — its
# opening figure at worst — so unlike an investment it is never unvalued.
# `valued_on` is null for the same reason: the balance is DERIVED at the date it is asked for rather
# than recorded on a date, so there is no valuation date to state and one would be an invented fact.
def _account_holding(account: Account, balance: Decimal, *, pot: Pot, rate_map) -> PotHoldingResponse:
    return _holding_response(account.id, account.name, account.currency, balance, account.is_active, pot=pot, rate_map=rate_map, valued_on=None)


# Lists everything a pot holds, with each holding's own figure and the same figure in the pot's base
# currency. Visible to whoever may see the pot at all, including a member holding 0% of it — partial
# visibility of something you co-own is not a feature (V5).
#
# Reuses the same two engines the NAV does — the latest snapshot on or before today, and the derived
# account balance — so a holding's figure here and its contribution to the NAV cannot disagree.
# Archived holdings are included and flagged: one still points at the pot, so it still blocks deleting
# it and still has to be movable back out.
async def list_holdings(session: AsyncSession, pot_id: int, user: User) -> PotHoldingsResponse:
    pot, _, _ = await require_visible(session, pot_id, user)
    investments, accounts = await pot_repository.list_holdings(session, pot.id)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    today = date_type.today()
    rate_map = lookup.get_rate_map_at(today)

    # Both batched: one snapshot query for every investment and one balance query set for every
    # account, so a pot holding twenty things costs the same as one holding two.
    snapshots = await snapshot_repository.get_latest_by_investments(session, [i.id for i in investments if i.id is not None], as_of_date=today)
    balances = await account_service.compute_account_balances_at(session, accounts, as_of_date=today)

    return PotHoldingsResponse(
        investments=[_investment_holding(i, snapshots.get(i.id), pot=pot, rate_map=rate_map) for i in investments],
        accounts=[_account_holding(a, balances.get(a.id, ZERO), pot=pot, rate_map=rate_map) for a in accounts],
    )


# The pot's value at each point of its cadence's grid, plus what the caller's own share was worth at
# each — the monitoring surface's whole subject (V5/X4).
#
# THE COST is the design. Valuing a pot at one date is ten queries (two holdings reads, one snapshot
# read and the seven-way account-balance union), so calling get_valuation once per point would make a
# twelve-point series a hundred-and-twenty-query page — §12's O3, arrived at from the read side. Every
# one of those reads is hoisted out of the loop instead: the holdings do not change per date, the
# snapshots come back for the whole window in one query, and the balances are accumulated per account
# over the window by compute_account_balance_series. The series therefore costs the same ten queries
# as a single valuation, whatever `periods` is.
#
# What it does NOT do is re-implement the valuation rule. Each point folds its figures through
# _add_holdings, the same function get_valuation uses, so a point is null in exactly the cases the NAV
# is null — which is legitimately most of the early points on a pot whose newest holding was
# snapshotted recently, and saying "we do not know" there is the whole reason that rule exists.
#
# Two bounds worth stating:
#   * the holdings are TODAY's holdings. There is no membership history for what a pot held when, so
#     the honest reading of an earlier point is "what the pot's current contents were worth then" —
#     the same reading GET /pots/{id}?as_of_date= already carries.
#   * the series starts at the pot's ANCHOR — its earliest ownership event, or its creation when the
#     ledger is empty — because a shared investment brings its whole snapshot history with it, and
#     without the bound a pot created yesterday would report years of "the pot's value" for a pot that
#     did not exist. A back-dated opening moves the anchor earlier, which is right: that is the date
#     the co-owners agreed their division began.
#
# `my_value` is null rather than zero while no units are outstanding. Before the baseline nobody owns
# any share of anything, and a zero would assert something the ledger has not said — the same rule
# ownership_percentages already applies to an undivided pot.
async def get_value_series(session: AsyncSession, pot_id: int, user: User, *, periods: int) -> PotValueSeriesResponse:
    pot, viewer, _ = await require_visible(session, pot_id, user)
    interval = series_interval(pot.snapshot_cadence)
    today = date_type.today()
    events = await pot_ownership_repository.list_by_pot(session, pot.id)
    anchor = min(events[0].date, pot.created_at.date(), today) if events else min(pot.created_at.date(), today)
    dates = [d for d in period_ends(today, interval, periods) if d >= anchor]

    investment_ids = await pot_repository.list_investment_ids(session, pot.id)
    accounts = [a for a in await pot_repository.list_accounts(session, pot.id) if a.id is not None]
    holds_anything = bool(investment_ids or accounts)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    snapshots = await snapshot_repository.list_by_investments(session, investment_ids, until=dates[-1])
    balances = await account_service.compute_account_balance_series(session, accounts, dates=dates)

    # Both walks are merges over already-sorted inputs — snapshots by (investment_id, date), events by
    # (date, id) — so each row is visited once across the whole series rather than once per point.
    snapshots_by_investment: dict[int, list[InvestmentSnapshot]] = {investment_id: [] for investment_id in investment_ids}
    for snapshot in snapshots:
        snapshots_by_investment[snapshot.investment_id].append(snapshot)
    cursors = dict.fromkeys(investment_ids, 0)
    latest: dict[int, InvestmentSnapshot | None] = dict.fromkeys(investment_ids)
    # Converted once for the whole series rather than per point: the ledger does not change between
    # dates, only how much of it has happened yet.
    entries = _as_entries(events)
    event_cursor = 0
    replayed: list = []

    points = []
    for index, point_date in enumerate(dates):
        for investment_id in investment_ids:
            rows = snapshots_by_investment[investment_id]
            cursor = cursors[investment_id]
            while cursor < len(rows) and rows[cursor].date <= point_date:
                latest[investment_id] = rows[cursor]
                cursor += 1
            cursors[investment_id] = cursor
        while event_cursor < len(events) and events[event_cursor].date <= point_date:
            replayed.append(entries[event_cursor])
            event_cursor += 1

        rate_map = lookup.get_rate_map_at(point_date)
        nav: Decimal | None = None
        if holds_anything:
            figures: list[tuple[Decimal, str] | None] = [
                None if latest[investment_id] is None else (latest[investment_id].value, latest[investment_id].currency)
                for investment_id in investment_ids
            ]
            nav = _add_holdings(ZERO, figures, pot.base_currency, rate_map)
            if nav is not None:
                nav = _add_holdings(nav, [(balances[a.id][index], a.currency) for a in accounts], pot.base_currency, rate_map)

        unit_balances = replay_units(replayed)
        my_value = None if nav is None or total_units(unit_balances) <= 0 else share_values(unit_balances, nav).get(viewer.id, ZERO)
        points.append(PotValueSeriesPoint(date=point_date, nav=nav, my_value=my_value))

    return PotValueSeriesResponse(interval=interval, points=points)


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
    snapshot_cadence: PotCadence = PotCadence.monthly,
    visibility: PotVisibility = PotVisibility.members,
) -> PotResponse:
    from app.services import group_service

    group, member = await group_service.require_admin(admin_session, group_id, user)
    existing = await pot_repository.list_by_group(admin_session, group.id)
    pot = Pot(
        group_id=group.id,
        name=name,
        base_currency=base_currency,
        snapshot_cadence=snapshot_cadence,
        visibility=visibility,
        # The first pot in a group is its default and needs no name; a second one always does.
        is_default=not existing,
    )
    pot = await pot_repository.create(admin_session, pot)
    await pot_repository.save_permission(admin_session, PotMemberPermission(pot_id=pot.id, member_id=member.id, can_view=True, can_write=True))
    await admin_session.commit()
    return await get_pot(admin_session, pot.id, user)


# Renames a pot, or changes how often it is expected to be re-valued or who may see it by default.
# Only provided fields are updated; base_currency is deliberately not among them, because it is the
# unit of every figure already recorded in the ledger.
# Group admin only — all three are configuration, not money movement, so they follow the membership
# rules rather than the pot's own write permission.
async def update_pot(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    name: str | None = None,
    snapshot_cadence: PotCadence | None = None,
    visibility: PotVisibility | None = None,
) -> PotResponse:
    from app.services import group_service

    pot, _, _ = await require_visible(session, pot_id, user)
    await group_service.require_admin(session, pot.group_id, user)
    if name is not None:
        pot.name = name
    if snapshot_cadence is not None:
        pot.snapshot_cadence = snapshot_cadence
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

    # Taking a holding OUT of a pot whose ownership is already agreed drops the pot's value by the
    # whole of that holding while nobody's units change — so every co-owner's share falls pro-rata
    # and the holding lands wholly in one person's private scope. That is one member taking joint
    # assets, with no cap on the amount, and it is the same violation §4.1 refuses for a cross-scope
    # transfer. Before the baseline exists nothing has been divided, so the move is free and undoing
    # a mistaken move-in still works. Afterwards it is a withdrawal or a buy-out, which redeem units.
    if not into and await pot_ownership_repository.list_by_pot(session, pot.id):
        raise PotAlreadyDividedError()

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
# Four checks, because none of them sees what the others do:
#   * linked_account_ids across the four PRIVATE movement tables — filtered by user_id, so it sees a
#     private account's own history and is the right question on the way in;
#   * linked_account_ids across the three GROUP-scoped ones — shared expenses, shared income and
#     settlements. Scope-free by construction: a group's row is nobody's private property, so there is
#     no user_id to filter by, and the caller can always see the ones that matter here because the
#     account being moved is their own and any group row naming it belongs to a group they are in.
#     Without these the hole is live and reachable: an account carrying ONLY shared rows passes every
#     private check, so moving it into a divided pot lands the whole of a distributed row's money in
#     the pot — raising every owner's share pro-rata while the splits still say the collector owes
#     each of them their share, so the same money is credited twice — and NULLs the user_id the row's
#     own edit path checks, which leaves a row the user can see and can no longer save;
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
        | await shared_expense_repository.linked_account_ids(session, account_ids)
        | await shared_income_repository.linked_account_ids(session, account_ids)
        | await group_settlement_repository.linked_account_ids(session, account_ids)
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
    pot_ids = [pot.id for group_id in group_ids for pot in await pot_repository.list_by_group(session, group_id)]
    if not pot_ids:
        return 0
    # Two statements for the whole set, not two per pot: account deletion is one use case and should
    # cost a fixed number of queries rather than one that grows with how much the leaver shared.
    moved = await investment_repository.reassign_pots_to_user(session, pot_ids, user_id)
    return moved + await account_repository.reassign_pots_to_user(session, pot_ids, user_id)
