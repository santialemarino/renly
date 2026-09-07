# Business logic for a pot's ownership ledger: the opening baseline, contributions, withdrawals and
# re-agreements.
#
# Three properties hold across every function here and are the reason the guards look the way they do:
#
#   * Balances are DERIVED. Nothing is stored as a running total, so recording an event never has to
#     correct a stored figure, and a back-dated event simply recomputes the series. That is why
#     back-dating is allowed here while account reconciliation is forward-only — a reconciliation
#     posts an adjustment ROW whose date changes recorded history, whereas this ledger is replayed.
#
#   * A movement needs a KNOWN price. Units are issued at the pot's value on the event's date, so an
#     event on a date the pot has no valuation for is refused rather than priced at a guess. Same
#     posture as reconciliation refusing to invent a figure.
#
#   * VALUE crosses a scope boundary here and NOWHERE else — money, and since contribute_holding a
#     whole holding as well. A transfer must stay within one scope because it is net-worth-neutral by
#     construction; moving joint money into a personal account is not neutral for the other owners.
#     The contribution and withdrawal mechanics are that same movement recorded honestly — for money,
#     the private leg really is debited and the pot leg really is credited, which is what makes the
#     pot's value move with it; for a holding, the holding itself moves and the pot's value moves
#     because the NAV then reads it. Either way the units issued are what say whose the value now is.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    NotFoundError,
    PotAlreadyOpenedError,
    PotBaseAmountRequiredError,
    PotEventNotConfirmableError,
    PotInsufficientUnitsError,
    PotMovementAccountInactiveError,
    PotMovementBeforeAccountOpenedError,
    PotNotOpenedError,
    PotPercentagesError,
    PotReagreementConfirmedError,
    PotReagreementNotYoursError,
    PotReagreementSameMemberError,
    PotUnsupportedMovementError,
    PotValuationRequiredError,
    PotWriteRequiredError,
    amount_for_units,
    opening_units,
    replay_units,
    share_values,
    total_units,
    unit_price,
    units_for_amount,
)
from app.domain.errors import AccountCurrencyMismatchError
from app.domain.pot import ONE_HUNDRED, OPENING_UNIT_PRICE, UNIT_PLACES, OwnershipEntry, quantize
from app.models.account import Account
from app.models.group import Group, GroupMember
from app.models.notification import NotificationEvent
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import account_repository, group_repository, pot_ownership_repository, pot_repository
from app.schemas.pot import PotOwnershipEventResponse
from app.services import exchange_rate_service, notification_service, pot_service, shared_audit_service
from app.utils.metrics import RateLookup

ZERO = Decimal(0)


# Turns ledger rows into the replay entries the unit math consumes, so the domain never imports a
# model and stays testable without a database.
def _as_entries(events: list[PotOwnershipEvent]) -> list[OwnershipEntry]:
    return [OwnershipEntry(member_id=e.member_id, units=e.units, counterparty_member_id=e.counterparty_member_id) for e in events]


# Which seat's agreement a re-agreement waits for, or None for an event that carries no confirmation.
#
# The AFFECTED seat, and only one of them: the member losing units, unless they recorded the change
# themselves, in which case it is the member receiving them. Written as one rule rather than a set of
# eligible seats because that is what makes the answer always be somebody who did NOT record the row —
# including the case a set would get wrong, a third party with write access recording a change between
# two other members, where the seat with something taken is the one whose agreement is worth having.
#
# Write access is deliberately absent, and that is the point of the whole unit (§29.1): write access is
# not granted by ownership — create_pot inserts can_write for the creator only — so a rule keyed on it
# would let whoever recorded the change also vouch for it.
#
# A name-only seat has no account, so a re-agreement whose affected seat is one is never confirmable by
# anybody and stays deletable by the real seat instead — D34's posture for a settlement, unchanged. The
# comparison is against `created_by`, which is SET NULL once that account is deleted: a NULL on either
# side leaves the answer on the GIVER, which is the seat with something taken and therefore the safe
# direction to fail in. The SQL policy mirrors this expression clause for clause.
def _confirming_member_id(event: PotOwnershipEvent, members_by_id: dict[int, GroupMember]) -> int | None:
    if event.type != OwnershipEventType.reagreement:
        return None
    giver = members_by_id.get(event.member_id)
    if giver is not None and giver.user_id is not None and giver.user_id == event.created_by:
        return event.counterparty_member_id
    return event.member_id


# Who may delete one ledger entry.
#
# Write access, as everywhere else in this file — EXCEPT that an UNCONFIRMED re-agreement may always be
# deleted by either seat it names, with or without it.
#
# That exception is not a convenience. Write access is not granted by ownership: create_pot inserts
# can_write for the CREATOR only, and recording the opening grants nobody else write. So the
# out-of-the-box state of a divided pot is that its creator can move units away from a co-owner, the
# co-owner is notified by name, and can do nothing about it — no reject, no undo, no appeal. That is
# the default configuration rather than an edge case, which is what makes the remedy load-bearing.
#
# It is deliberately narrow in three ways. Only a RE-AGREEMENT, because that is the only event type
# that moves value between two people without money changing hands — a contribution or a withdrawal
# moves the mover's own money, and an opening is the division everyone agreed to. Only the two seats it
# NAMES, never any other member. And only DELETE: the counterparty gains no ability to record anything,
# which the row-level policy enforces separately by keeping its WITH CHECK on write access.
#
# CONFIRMATION closes it again, and closes it for EVERYBODY including a pot writer — which is what makes
# confirming the trust anchor rather than a label. The re-agreement counted from the moment it was
# recorded either way (an unapplied one would leave the pot showing percentages everyone agrees are
# wrong), so what confirmation changes is not the arithmetic but who may undo it. The way back out is
# the affected seat un-confirming, and nothing else.
#
# ONE rule, asked by the write and read off the response as `can_delete`, so the button offered and the
# answer given cannot disagree. `delete_event` picks WHICH refusal to raise from the row's state.
def _may_delete_event(event: PotOwnershipEvent, viewer_member_id: int, *, may_write: bool) -> bool:
    if event.confirmed_at is not None:
        return False
    if may_write:
        return True
    return event.type == OwnershipEventType.reagreement and viewer_member_id in (event.member_id, event.counterparty_member_id)


# Builds one ledger response, naming both members rather than exposing raw seat ids alone — a client
# rendering a movement history needs the names, and a second round trip per row to get them would be
# an N+1 pushed onto the frontend.
#
# The three permission fields are resolved HERE rather than by the client, because the confirm rule
# reads `created_by` — a column the response deliberately does not expose — so the web could not derive
# it at all, and `can_delete` joins them for the reason GroupSettlementResponse resolves its own pair:
# a second copy of a permission check is a second thing that can disagree with the gate that decides.
def _build_response(
    event: PotOwnershipEvent, members_by_id: dict[int, GroupMember], *, viewer_member_id: int, may_write: bool
) -> PotOwnershipEventResponse:
    confirming_member_id = _confirming_member_id(event, members_by_id)
    is_confirming_seat = confirming_member_id is not None and confirming_member_id == viewer_member_id
    counterparty = members_by_id.get(event.counterparty_member_id) if event.counterparty_member_id is not None else None
    return PotOwnershipEventResponse(
        id=event.id,
        pot_id=event.pot_id,
        type=event.type,
        date=event.date,
        member_id=event.member_id,
        member_name=members_by_id[event.member_id].display_name if event.member_id in members_by_id else "",
        counterparty_member_id=event.counterparty_member_id,
        counterparty_name=counterparty.display_name if counterparty is not None else None,
        amount=event.amount,
        amount_currency=event.amount_currency,
        base_amount=event.base_amount,
        units=event.units,
        unit_price=event.unit_price,
        from_account_id=event.from_account_id,
        to_account_id=event.to_account_id,
        confirmed_at=event.confirmed_at,
        can_confirm=is_confirming_seat and event.confirmed_at is None,
        can_unconfirm=is_confirming_seat and event.confirmed_at is not None,
        can_delete=_may_delete_event(event, viewer_member_id, may_write=may_write),
        notes=event.notes,
        created_at=event.created_at,
    )


# Resolves an ACTIVE seat in the pot's group, or raises NotFoundError. Every member id reaching this
# service comes from a request body, so it is checked against the pot's own group rather than trusted
# — a seat id from another group would otherwise silently attach that group's member to this ledger.
async def _require_seat(session: AsyncSession, pot: Pot, member_id: int) -> GroupMember:
    member = await group_repository.get_member(session, pot.group_id, member_id)
    if member is None or not member.is_active:
        raise NotFoundError("Group member not found")
    return member


# The pot's unit price on a date, or a refusal. Bundles the two ways it can be undefined into the two
# errors that describe them: no units outstanding (the pot has no baseline) and no usable valuation.
# `lookup` is optional so a caller that needs the rates for something else too builds exactly one per
# request, which is the layering rule for rate lookups. Left unset it builds its own, which is what the
# two paths that need nothing else do.
async def _require_price(
    session: AsyncSession, pot: Pot, user: User, as_of_date: date_type, *, lookup: RateLookup | None = None
) -> tuple[Decimal, dict[int, Decimal]]:
    events = await pot_ownership_repository.list_by_pot(session, pot.id, as_of_date=as_of_date)
    balances = replay_units(_as_entries(events))
    outstanding = total_units(balances)
    if outstanding <= 0:
        raise PotNotOpenedError()
    if lookup is None:
        lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    nav = await pot_service.get_nav(session, pot, as_of_date=as_of_date, lookup=lookup)
    if nav is None:
        raise PotValuationRequiredError(as_of_date)
    price = unit_price(nav, outstanding)
    if price is None:
        raise PotValuationRequiredError(as_of_date)
    return (price, balances)


# Validates one leg of a movement and returns the account, or None when no account was named.
# `expect_shared` says which side of the boundary this leg must sit on, and both halves matter:
#   * the PRIVATE leg must belong to the moving member's own account, or one member could move money
#     out of another's account by naming its id;
#   * the POT leg must belong to THIS pot, or a contribution would credit a different pot entirely.
#
# EACH leg must also be in the currency of the figure that will move its balance, and the two figures
# are different columns: the pot leg's is `base_amount` (so it must be in the pot's base currency,
# which is what makes base_amount unambiguous) and the private leg's is `amount` (so it must be in
# `private_currency`). Without the second half a movement could subtract an ARS figure from a USD
# account — merged constraint (a), "entry currency = account currency", which the pot leg already had
# and the private leg did not.
async def _require_leg(
    session: AsyncSession,
    pot: Pot,
    user: User,
    account_id: int | None,
    *,
    expect_shared: bool,
    private_currency: str,
) -> Account | None:
    if account_id is None:
        return None
    account = await account_repository.get_by_id_any_scope(session, account_id)
    if account is None:
        raise NotFoundError("Account not found")
    if expect_shared:
        if account.pot_id != pot.id:
            raise NotFoundError("Account not found")
        # An archived pot account is excluded from the NAV but not from the balance union, so routing
        # money through one moves the account and leaves the pot's value where it was — units issued
        # against nothing. Refused here rather than at the holdings gate, because whether an archived
        # holding may be SHARED at all is a separate question this does not answer.
        if not account.is_active:
            raise PotMovementAccountInactiveError(account.id)
        if account.currency != pot.base_currency:
            # Arguments in the canonical order: the figure's currency first, the account's second. The
            # reverse reports the pot's base currency AS the account's, which is a message that states
            # something untrue about the very account the caller named.
            raise AccountCurrencyMismatchError(pot.base_currency, account.currency)
    else:
        if account.user_id != user.id:
            raise NotFoundError("Account not found")
        if account.currency != private_currency:
            raise AccountCurrencyMismatchError(private_currency, account.currency)
    return account


# Refuses a movement dated before one of the accounts it names existed.
#
# Each leg of the balance union is bounded by its OWN account's opening_date, because opening_balance
# already IS the balance at that date. So a movement dated earlier issues or redeems units while the
# account it supposedly moved the money through never changes — value appearing in the pot from
# nowhere. Exactly what _ensure_both_accounts_open does for transfers, and worse here because units
# are issued against it.
# Takes the resolved rows rather than ids, so it can only be called after both legs are validated, and
# skips whichever legs were not named (money may legitimately arrive from outside Renly).
def _ensure_accounts_open(accounts: list[Account | None], date: date_type) -> None:
    openings = [a.opening_date for a in accounts if a is not None]
    if not openings:
        return
    latest = max(openings)
    if date < latest:
        raise PotMovementBeforeAccountOpenedError(latest)


# Divides `total` across a pot's owners in their proportions ON `date`, or returns {} when the pot has
# no units outstanding then.
#
# `share_values` is the same function the pot page divides a NAV with, so the parts sum to the total
# exactly and the rounding rule cannot differ between the two surfaces.
#
# Shared by the two flow paths that need it — money a shared account FRONTED for an expense and money
# a shared account RECEIVED as income — because it is one rule and a second copy is a thing that can
# be wrong on its own. It deliberately performs NO policy check and raises nothing: whether the pot
# belongs to the caller's group, and what to say when it is undivided, are questions whose ANSWERS are
# the same for both flows but whose WORDING is not ("who paid" and "who the money reached" are
# different instructions). So each caller checks the pot's group and names its own refusal, and only
# the arithmetic lives here.
#
# Runs on whatever session it is given and applies no visibility check of its own: both callers have
# already resolved the account whose pot this is, through a policy that let them see it.
async def owner_shares(session: AsyncSession, pot: Pot, *, total: Decimal, date: date_type) -> dict[int, Decimal]:
    events = await pot_ownership_repository.list_by_pot(session, pot.id, as_of_date=date)
    return share_values(replay_units(_as_entries(events)), total)


# Who hears about a change to this pot: everyone who may SEE it, minus whoever made the change.
# `pot_service.list_notifiable_user_ids` is the pot's own visibility rule, so an 'owners' pot never
# announces itself to a member who cannot see it — the notification would otherwise disclose exactly
# what the policy hides.
async def _pot_audience(session: AsyncSession, pot: Pot, user: User) -> list[int]:
    return await pot_service.list_notifiable_user_ids(session, pot, exclude_user_id=user.id)


# The payload every pot notification carries, plus whatever the specific event adds.
#
# `pot` is the pot's raw name and may be NULL — a group's default pot has none — and it is left NULL
# rather than filled in here, because the label a nameless pot reads under is LOCALIZED while this
# payload is shared by every recipient whatever language each of them uses. Each renderer applies its
# own fallback in the reader's own language: `notification_templates._readable` for email and push,
# and `notificationRow`'s `potFallback` on the web for the feed.
def _pot_payload(pot: Pot, group: Group | None, extra: dict) -> dict:
    return {"group_id": pot.group_id, "group": group.name if group else None, "pot_id": pot.id, "pot": pot.name, **extra}


# One ledger audit entry. `variant` is the event's own type, so the four movements share one action and
# one sentence with four readings rather than four actions — the split the notification layer already
# made between an event and its variant.
#
# Every entry carries `pot_id`, which is what makes it as hidden as the pot itself: a member who cannot
# see an 'owners' pot must not read its movements off the group's activity feed either.
async def _audit(
    session: AsyncSession,
    pot: Pot,
    user: User,
    action: AuditAction,
    *,
    event_id: int | None,
    variant: OwnershipEventType,
    **payload,
) -> None:
    await shared_audit_service.record(
        session,
        group_id=pot.group_id,
        actor=user,
        entity_type=AuditEntityType.ownership_event,
        action=action,
        entity_id=event_id,
        pot_id=pot.id,
        payload={"pot": pot.name, "variant": variant.value, **payload},
    )


# Lists a pot's ownership ledger in replay order. Visible to whoever may see the pot at all: a member
# holding 0% still sees every movement, because partial visibility of something you co-own is not a
# feature (V5).
async def list_events(session: AsyncSession, pot_id: int, user: User) -> list[PotOwnershipEventResponse]:
    pot, viewer, permission = await pot_service.require_visible(session, pot_id, user)
    events = await pot_ownership_repository.list_by_pot(session, pot.id)
    members = await group_repository.list_members(session, pot.group_id)
    members_by_id = {m.id: m for m in members}
    may_write = pot_service.may_write(permission)
    return [_build_response(e, members_by_id, viewer_member_id=viewer.id, may_write=may_write) for e in events]


# Records the pot's opening baseline: a value and each owner's percentage on a date, issuing units at
# a nominal 1.00 so the opening unit count reads back as the percentage it was entered as.
# This IS the division — nothing before its date is in scope, the same anchor accounts.opening_balance
# and opening_date are — so there can be only one, and changing the split afterwards is a
# re-agreement rather than a second baseline.
async def record_opening(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    date: date_type,
    value: Decimal,
    shares: dict[int, Decimal],
    notes: str | None = None,
) -> list[PotOwnershipEventResponse]:
    pot, actor = await pot_service.require_writable(session, pot_id, user)
    # Locked before the ledger is read, and this is the case that shows why: "is it already opened" is
    # answered by a SELECT and acted on by an INSERT, so two openings recorded at the same moment both
    # find an empty ledger and the pot ends up divided twice — a split summing to 200%, which no later
    # act can repair, because record_opening then refuses while any opening row survives.
    await pot_repository.lock(session, pot.id)
    existing = await pot_ownership_repository.list_by_pot(session, pot.id)
    if existing:
        raise PotAlreadyOpenedError()
    total = sum(shares.values(), ZERO)
    if total != ONE_HUNDRED:
        raise PotPercentagesError(total)

    # The whole roster in ONE query, then validated in memory — an opening names every owner, so a
    # seat lookup per member is an N+1 that grows with the group.
    members_by_id = {m.id: m for m in await group_repository.list_members(session, pot.group_id)}
    for member_id in shares:
        member = members_by_id.get(member_id)
        if member is None or not member.is_active:
            raise NotFoundError("Group member not found")

    units_by_member = opening_units(value, shares)
    # Built in memory and written in one batch: an opening is one row per owner, and flushing per row
    # is a round trip per owner for what is a single indivisible act.
    created = await pot_ownership_repository.create_many(
        session,
        [
            PotOwnershipEvent(
                pot_id=pot.id,
                type=OwnershipEventType.opening,
                date=date,
                member_id=member_id,
                base_amount=amount_for_units(units, OPENING_UNIT_PRICE),
                units=units,
                unit_price=OPENING_UNIT_PRICE,
                notes=notes,
                created_by=user.id,
            )
            for member_id, units in units_by_member.items()
        ],
    )
    # Resolved BEFORE the commit, deliberately. Every producer in this initiative reads its recipients
    # and its payload while the transaction is still open, so a failure in those reads fails the whole
    # use case with nothing written — an honest error — rather than 500-ing a request whose money write
    # has already landed. After the commit only dispatch() runs, and that swallows everything.
    # `event_id=None` alone among the ledger's entries, and deliberately: an opening is ONE act written
    # as one row per owner, so there is no single id that names it. Deleting it takes the whole baseline
    # for the same reason.
    await _audit(session, pot, user, AuditAction.created, event_id=None, variant=OwnershipEventType.opening)
    recipients = await _pot_audience(session, pot, user)
    group = await group_repository.get_by_id(session, pot.group_id)
    await session.commit()

    # Everyone who can SEE the pot is told it now has a division: the answer to "what do I own here"
    # changed from nothing to a percentage.
    await notification_service.dispatch(
        NotificationEvent.ownership_changed,
        recipients,
        _pot_payload(pot, group, {"variant": "opening", "actor": actor.display_name}),
    )
    return [_build_response(e, members_by_id, viewer_member_id=actor.id, may_write=True) for e in created]


# Records a contribution or a withdrawal: money crossing the scope boundary, priced at the pot's unit
# price on the date, issuing or redeeming units for the member who moved it.
# A contribution dilutes everyone's PERCENTAGE and nobody's VALUE, which is the whole reason units
# exist — percentages alone cannot express "he added 5 and nobody else lost anything".
async def record_movement(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    type: OwnershipEventType,
    date: date_type,
    member_id: int,
    amount: Decimal,
    amount_currency: str | None = None,
    base_amount: Decimal | None = None,
    from_account_id: int | None = None,
    to_account_id: int | None = None,
    whole_share: bool = False,
    notes: str | None = None,
) -> PotOwnershipEventResponse:
    if type not in (OwnershipEventType.contribution, OwnershipEventType.withdrawal):
        raise PotUnsupportedMovementError(type)
    pot, actor = await pot_service.require_writable(session, pot_id, user)
    # Locked before the price and the balances are derived. Both are read-then-act: the unit price is
    # what the new units are issued at, and a withdrawal is refused for more than the member holds — so
    # two withdrawals racing each other both measure a balance neither will still have, and between
    # them redeem more units than exist.
    await pot_repository.lock(session, pot.id)
    member = await _require_seat(session, pot, member_id)
    price, balances = await _require_price(session, pot, user, date)

    is_contribution = type == OwnershipEventType.contribution
    # Both amounts are stored and no rate ever is, matching transfers and card_settlements: a
    # cross-currency move records what left and what was credited, and which one a sum reads depends
    # on the sum's side.
    currency = amount_currency or pot.base_currency
    credited = base_amount if currency != pot.base_currency else amount
    if credited is None:
        # A missing field, not a mismatch: nothing here disagrees with anything, the caller simply has
        # not said what the pot was credited — and deriving it would mean storing a rate.
        raise PotBaseAmountRequiredError(currency, pot.base_currency)

    source = await _require_leg(session, pot, user, from_account_id, expect_shared=not is_contribution, private_currency=currency)
    destination = await _require_leg(session, pot, user, to_account_id, expect_shared=is_contribution, private_currency=currency)
    _ensure_accounts_open([source, destination], date)

    units = units_for_amount(credited, price)
    if not is_contribution:
        held = balances.get(member.id, ZERO)
        if whole_share:
            # Taking the WHOLE share redeems the member's balance exactly, rather than dividing money
            # by a price and hoping the quotient lands on it. It almost never does: over 224,200
            # plausible pots, an amount derived from the reported share value or from units x price
            # redeemed the balance exactly 4.6% of the time — refused 48.6% of the time
            # (pot_insufficient_units, for asking to take out precisely what you own) and leaving a
            # residual the other 46.8%. A residual is not cosmetic: replay_units drops only an EXACT
            # zero, so 0.000001 units survives as a 0.00% owner worth 0.00, on every screen, forever.
            #
            # `amount` still records what money actually moved and is not re-derived from the units.
            # The two may honestly disagree — someone may accept less than their share is worth to
            # exit — and the event stores unit_price, so the ledger says which is which. Nobody else's
            # units change either way: a withdrawal only ever redeems its own member's.
            # A member who holds nothing has no whole share to take, and writing the event anyway
            # would put a zero-unit row on the history forever. Not reachable from any surface — every
            # picker that names a member for this offers holders only — so it reuses the units error
            # rather than earning a code of its own; the localized message ("That is more than that
            # person holds") stays true, and only the English detail's figures read oddly at 0.
            if held <= 0:
                raise PotInsufficientUnitsError(held, units)
            units = held
        elif units > held:
            raise PotInsufficientUnitsError(held, units)
        units = -units

    event = await pot_ownership_repository.create(
        session,
        PotOwnershipEvent(
            pot_id=pot.id,
            type=type,
            date=date,
            member_id=member.id,
            amount=amount,
            amount_currency=amount_currency if currency != pot.base_currency else None,
            base_amount=credited,
            units=units,
            unit_price=price,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            notes=notes,
            created_by=user.id,
        ),
    )
    await _audit(
        session,
        pot,
        user,
        AuditAction.created,
        event_id=event.id,
        variant=type,
        member=member.display_name,
        # The credited figure in the pot's base currency, matching what the notification says and for
        # the same reason: what changed for every reader is what the pot took in or paid out, and a
        # cross-currency movement's two figures are different numbers in different currencies.
        amount=str(credited),
        currency=pot.base_currency,
    )
    recipients = await _pot_audience(session, pot, user)
    group = await group_repository.get_by_id(session, pot.group_id)
    await session.commit()

    # The figure notified is `credited` in the POT's base currency, not the source `amount`: what
    # changed for every reader is what the pot took in or paid out, and a cross-currency movement's two
    # figures are different numbers in different currencies. The member NAMED is whose units moved,
    # which is not necessarily the person who recorded it.
    await notification_service.dispatch(
        NotificationEvent.pot_movement,
        recipients,
        _pot_payload(
            pot,
            group,
            {
                "variant": type.value,
                "member": member.display_name,
                "amount": str(credited),
                "currency": pot.base_currency,
            },
        ),
    )
    return _build_response(event, {member.id: member}, viewer_member_id=actor.id, may_write=True)


# Records a HOLDING contributed to a divided pot: an investment or a cash account moving out of the
# caller's private scope and into the pot, valued where it stands and paid for in units.
#
# This is the fourth guided flow, and it replaces a refusal. Moving a holding into a divided pot on its
# own raises the pot's value while nobody's units change, so what came wholly out of one person's scope
# is gifted pro-rata to every owner — silently. What makes it honest is the pairing: the units issued
# are the holding's value divided by the price the pot's EXISTING holdings set, so the contributor's new
# share is worth exactly what they put in and nobody else's value moves at all. Only percentages do,
# which is what units are for.
#
# Three properties are load-bearing and each is a defect if it goes:
#
#   * THE PRICE IS READ BEFORE THE HOLDING MOVES. A moment later the NAV includes it, so pricing after
#     the move would divide the pot's new value by its old unit count and issue the contributor units
#     at an inflated price — they would pay for their own contribution twice over, and the difference
#     would go to everybody else. The lock, the price and the move are ordered here and nowhere else.
#   * THE DATE IS TODAY, and it is not a field. A holding has no pot-membership history — the NAV reads
#     whatever the pot holds NOW at every date it is asked about — so pricing at an earlier date issues
#     units for what the holding was worth THEN against an asset the pot gains at what it is worth NOW.
#     The difference is handed out, or taken, pro-rata: the very transfer this flow exists to close.
#     A money contribution has no such gap, because account balances are derived and the money really
#     was in the pot's account from the date it moved.
#   * THE SEAT IS THE CALLER'S OWN, and it is not a field either. The holding is theirs — nothing else
#     passes require_contributable_holding — so recording it for another member would record that they
#     contributed an asset they do not own.
#
# It reuses the `contribution` event type rather than earning one of its own. Nothing behaves
# differently on the type (the replay, the ledger's amount rule, the outgoing-sign rule, the
# notification and audit variants, the delete-permission rule and the movements endpoint's guard all
# read it the same way), and U4's distinction is contribution-versus-GIFT, which this preserves exactly:
# units are issued for the whole of the value, so nothing is given away. The row carries the holding's
# own figure and currency in `amount`, the pot's in `base_amount`, and names no account legs — money
# moved between no accounts, because the asset itself moved.
async def contribute_holding(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    investment_id: int | None = None,
    account_id: int | None = None,
    notes: str | None = None,
) -> PotOwnershipEventResponse:
    pot, member = await pot_service.require_writable(session, pot_id, user)
    # Locked before anything is read, because two things here are read-then-act: the unit price the
    # units are issued at, and the pot's holdings the NAV behind it is summed from. Two contributions a
    # moment apart would otherwise each price themselves against a pot that does not yet hold the
    # other's asset, and between them issue units at a price neither of them ends up at.
    await pot_repository.lock(session, pot.id)
    holding = await pot_service.require_contributable_holding(session, user, investment_id=investment_id, account_id=account_id)

    # One lookup for the whole request, shared by the pot's price and the holding's conversion — the
    # two figures are divided by each other, so a second lookup would be a second set of rates on
    # opposite sides of the same division.
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    today = date_type.today()
    price, _ = await _require_price(session, pot, user, today, lookup=lookup)
    valued = await pot_service.value_contributed_holding(session, pot, holding, as_of_date=today, lookup=lookup, price=price)

    credited = valued.base_value
    event = await pot_ownership_repository.create(
        session,
        PotOwnershipEvent(
            pot_id=pot.id,
            type=OwnershipEventType.contribution,
            date=today,
            member_id=member.id,
            amount=valued.value,
            # Null whenever the holding is already in the pot's currency, exactly as a money movement
            # stores it: a row with a currency set always means a real conversion happened.
            amount_currency=valued.currency if valued.currency != pot.base_currency else None,
            base_amount=credited,
            units=units_for_amount(credited, price),
            unit_price=price,
            notes=notes,
            created_by=user.id,
        ),
    )
    # Only now. Everything above had to see the pot WITHOUT this holding in it.
    await pot_service.attach_holding(session, pot, holding)

    # ONE audit entry, not two. The act changed two tables, but a `holdings_added` entry beside this one
    # would put two lines in the group's feed for a single act — and the entry that says value arrived
    # and whose units moved is the one that describes it. The holding's own name stays out of the trail
    # for PR 10's reason: an entry is permanent and a holding's label may be private again later.
    await _audit(
        session,
        pot,
        user,
        AuditAction.created,
        event_id=event.id,
        variant=OwnershipEventType.contribution,
        member=member.display_name,
        amount=str(credited),
        currency=pot.base_currency,
    )
    recipients = await _pot_audience(session, pot, user)
    group = await group_repository.get_by_id(session, pot.group_id)
    await session.commit()

    # The same sentence a money contribution sends, and deliberately: what changed for every reader is
    # that the pot took in this much and one person's share grew by it. Which KIND of thing arrived is
    # on the pot page, where the holdings list now names it.
    await notification_service.dispatch(
        NotificationEvent.pot_movement,
        recipients,
        _pot_payload(
            pot,
            group,
            {
                "variant": OwnershipEventType.contribution.value,
                "member": member.display_name,
                "amount": str(credited),
                "currency": pot.base_currency,
            },
        ),
    )
    return _build_response(event, {member.id: member}, viewer_member_id=member.id, may_write=True)


# Records a re-agreement: units moving from one member to another with no money at all. Net-zero in
# units by construction — the counterparty receives exactly the negation — because this is people
# agreeing to a different split of the same pot, not value entering or leaving it.
# Taken as a PERCENTAGE of the whole pot rather than a unit count, because U2 is that percentages go
# in and percentages come out; a raw unit count appears nowhere a person can see.
#
# `percentage=None` means the WHOLE of the giver's stake, which is a distinct input rather than sugar
# for "their current share as a percentage": that figure has to be rounded to NUMERIC(5,2) and then
# multiplied back out by the units outstanding, and it reproduced the giver's exact balance 18 times
# in 200,000 plausible pots. The other 199,982 split evenly between the API refusing a full buy-out
# (pot_insufficient_units, for asking to move precisely what the seller owns) and the seller keeping a
# residual — and a residual is not cosmetic, because replay_units drops only an EXACT zero, so
# 0.000001 units survives as a 0.00% owner worth 0.00, on every screen, forever.
# One nullable parameter rather than a percentage plus a flag, so there is no state where both or
# neither is stated and nothing to narrow before use. The request boundary carries the pair
# (`whole_share`) and PotReagreementCreate is what refuses both-or-neither.
async def record_reagreement(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    date: date_type,
    from_member_id: int,
    to_member_id: int,
    percentage: Decimal | None,
    notes: str | None = None,
) -> PotOwnershipEventResponse:
    pot, actor = await pot_service.require_writable(session, pot_id, user)
    # Locked for the same reason a movement is: the giver's balance is read and then acted on, so two
    # re-agreements moving the same stake would each find it intact and between them hand out more than
    # the giver owns.
    await pot_repository.lock(session, pot.id)
    giver = await _require_seat(session, pot, from_member_id)
    receiver = await _require_seat(session, pot, to_member_id)
    if giver.id == receiver.id:
        raise PotReagreementSameMemberError()
    price, balances = await _require_price(session, pot, user, date)

    held = balances.get(giver.id, ZERO)
    if percentage is None:
        # Same as the withdrawal's: no stake to hand over, and no surface can ask for one — the giver
        # picker in both the guided buy-out and the manual change-of-split lists holders only.
        if held <= 0:
            raise PotInsufficientUnitsError(held, held)
        moved = held
    else:
        moved = quantize(total_units(balances) * percentage / ONE_HUNDRED, UNIT_PLACES)
        if moved > held:
            raise PotInsufficientUnitsError(held, moved)

    event = await pot_ownership_repository.create(
        session,
        PotOwnershipEvent(
            pot_id=pot.id,
            type=OwnershipEventType.reagreement,
            date=date,
            member_id=giver.id,
            counterparty_member_id=receiver.id,
            # Signed against member_id like every other event, so the replay needs no per-type rule:
            # the giver loses, and the counterparty receives exactly the negation.
            units=-moved,
            unit_price=price,
            notes=notes,
            created_by=user.id,
        ),
    )
    await _audit(
        session,
        pot,
        user,
        AuditAction.created,
        event_id=event.id,
        variant=OwnershipEventType.reagreement,
        member=giver.display_name,
        counterparty=receiver.display_name,
    )
    recipients = await _pot_audience(session, pot, user)
    group = await group_repository.get_by_id(session, pot.group_id)
    await session.commit()

    # No figure at all, and that is deliberate rather than an omission. What moved is a number of UNITS
    # — a quantity no surface shows a person (U2: percentages go in and percentages come out) — and the
    # percentage it corresponds to is not stored on the event, so any figure here would have to be
    # re-derived from the ledger and would then be a second answer to a question the pot page already
    # answers. It says who gave to whom, and the pot page says how much.
    await notification_service.dispatch(
        NotificationEvent.ownership_changed,
        recipients,
        _pot_payload(
            pot,
            group,
            {
                "variant": "reagreement",
                "actor": actor.display_name,
                "from_member": giver.display_name,
                "to_member": receiver.display_name,
            },
        ),
    )
    return _build_response(event, {giver.id: giver, receiver.id: receiver}, viewer_member_id=actor.id, may_write=True)


# Resolves the re-agreement a confirm or an un-confirm names, together with the caller's seat and
# whether the caller is the seat whose agreement it waits for.
#
# Gated on require_VISIBLE rather than require_writable, exactly as delete_event is and for the same
# reason: the affected seat is usually the one WITHOUT write access, so asking the write question here
# would refuse the only person entitled to answer.
#
# Locks the POT, because both callers read a state and act on it — the confirm reads `confirmed_at` and
# then sets it — and because a deletion racing a confirmation must land wholly before or wholly after
# it, never between the read and the write. The pot rather than the row: every other ledger write locks
# the pot, and two lock orders that can meet is how a deadlock is built.
async def _require_confirmable(
    session: AsyncSession, pot_id: int, event_id: int, user: User
) -> tuple[Pot, PotOwnershipEvent, GroupMember, dict[int, GroupMember], bool]:
    pot, viewer, permission = await pot_service.require_visible(session, pot_id, user)
    await pot_repository.lock(session, pot.id)
    event = await pot_ownership_repository.get_by_id(session, pot.id, event_id)
    if event is None:
        raise NotFoundError("Ownership event not found")
    if event.type != OwnershipEventType.reagreement:
        raise PotEventNotConfirmableError()
    members_by_id = {member.id: member for member in await group_repository.list_members(session, pot.group_id)}
    if _confirming_member_id(event, members_by_id) != viewer.id:
        raise PotReagreementNotYoursError()
    return (pot, event, viewer, members_by_id, pot_service.may_write(permission))


# One announcement for a confirmation or its withdrawal, addressed to everyone who may see the pot
# minus whoever acted.
#
# It reuses `ownership_changed` with a variant rather than earning an event of its own — the same
# choice the deletion made, and for the same reason: somebody who has switched pot-ownership news off
# stays switched off for the confirmation too, and `notification_event` is a Postgres enum, so a new
# value would be a migration for a sentence.
#
# It names both seats and no figure. What was agreed is a change of split whose size the pot page
# already states in percentages; a units figure appears nowhere a person can see (U2), and a second
# answer to a question the pot page answers is how two surfaces come to disagree.
async def _announce_confirmation(
    session: AsyncSession, pot: Pot, event: PotOwnershipEvent, members_by_id: dict[int, GroupMember], actor: GroupMember, user: User, variant: str
) -> None:
    recipients = await pot_service.list_notifiable_user_ids(session, pot, exclude_user_id=user.id)
    group = await group_repository.get_by_id(session, pot.group_id)
    giver = members_by_id.get(event.member_id)
    receiver = members_by_id.get(event.counterparty_member_id) if event.counterparty_member_id is not None else None
    await notification_service.dispatch(
        NotificationEvent.ownership_changed,
        recipients,
        _pot_payload(
            pot,
            group,
            {
                "variant": variant,
                "actor": actor.display_name,
                "from_member": giver.display_name if giver is not None else None,
                "to_member": receiver.display_name if receiver is not None else None,
            },
        ),
    )


# Confirms a re-agreement: the affected seat agreeing to the split that was recorded for them.
#
# It changes no arithmetic. The re-agreement counted from the moment it was recorded and still does —
# PR 3 rejected a PENDING gate on exactly that ground, because an unapplied re-agreement leaves the pot
# showing percentages everybody agrees are wrong, so BOTH states would lie. What this changes is who
# may undo it: unconfirmed, either named seat may delete it (the remedy PR 10 shipped, which exists
# because write access is not granted by ownership); confirmed, nobody may until this same seat takes
# their word back. Same shape as a settlement's payee-confirm (D28), and the trust anchor rather than
# a permission.
async def confirm_event(session: AsyncSession, pot_id: int, event_id: int, user: User) -> PotOwnershipEventResponse:
    pot, event, viewer, members_by_id, may_write = await _require_confirmable(session, pot_id, event_id, user)
    if event.confirmed_at is not None:
        raise PotReagreementConfirmedError()
    event.confirmed_at = utcnow()
    await pot_ownership_repository.save(session, event)
    await _audit(
        session,
        pot,
        user,
        AuditAction.confirmed,
        event_id=event.id,
        variant=event.type,
        member=members_by_id[event.member_id].display_name if event.member_id in members_by_id else None,
        counterparty=members_by_id[event.counterparty_member_id].display_name if event.counterparty_member_id in members_by_id else None,
    )
    await session.commit()
    await session.refresh(event)
    await _announce_confirmation(session, pot, event, members_by_id, viewer, user, "confirmed")
    return _build_response(event, members_by_id, viewer_member_id=viewer.id, may_write=may_write)


# Takes a confirmation back, returning the re-agreement to deletable so it can be corrected or removed.
# Only the seat that gave it may, for the same reason only they could give it: it is their word being
# withdrawn. It is also the ONLY way out of a confirmed re-agreement, which nobody can delete — left
# underivable, one confirmed by mistake would have no exit at all.
async def unconfirm_event(session: AsyncSession, pot_id: int, event_id: int, user: User) -> PotOwnershipEventResponse:
    pot, event, viewer, members_by_id, may_write = await _require_confirmable(session, pot_id, event_id, user)
    # Mirrors unconfirm_settlement's answer for the same state: there is no confirmation here to take
    # back, and nothing in the app offers the action on a row that has none.
    if event.confirmed_at is None:
        raise NotFoundError("Confirmation not found")
    event.confirmed_at = None
    await pot_ownership_repository.save(session, event)
    await _audit(
        session,
        pot,
        user,
        AuditAction.unconfirmed,
        event_id=event.id,
        variant=event.type,
        member=members_by_id[event.member_id].display_name if event.member_id in members_by_id else None,
        counterparty=members_by_id[event.counterparty_member_id].display_name if event.counterparty_member_id in members_by_id else None,
    )
    await session.commit()
    await session.refresh(event)
    # Announced as well, unlike a settlement's un-confirm, which tells nobody. Withdrawing a
    # confirmation RE-ARMS a deletion the lock had closed off, so the other seat's standing genuinely
    # changes — and they cannot see it happen on a page they are not looking at.
    await _announce_confirmation(session, pot, event, members_by_id, viewer, user, "unconfirmed")
    return _build_response(event, members_by_id, viewer_member_id=viewer.id, may_write=may_write)


# Deletes an ownership event. Balances are derived, so removing one recomputes the series with no
# stored total to correct — the same property that makes back-dating safe.
#
# An OPENING takes the whole baseline with it, because the baseline is one act written as one row per
# owner. Deleting a single row of it leaves a division summing to less than the value it recorded and
# silently hands the remaining owners a share nobody agreed to — and it cannot be repaired, because
# record_opening refuses while any opening row survives, so the only way back would be a re-agreement,
# which records a gift that never happened. One act in, one act out.
#
# Gated on require_VISIBLE rather than require_writable, with the write check moved into
# _may_delete_event: the counterparty remedy above is the one act here that write access does not
# govern, and asking the wider question first is what lets a single function answer both.
#
# Returns how many events went, so a caller can say so.
async def delete_event(session: AsyncSession, pot_id: int, event_id: int, user: User) -> int:
    pot, viewer, permission = await pot_service.require_visible(session, pot_id, user)
    # Locked like every other ledger write. A deletion changes what the next unit price is derived from,
    # so a movement pricing itself against this pot at the same moment must see the ledger either wholly
    # before or wholly after — never a state in between.
    await pot_repository.lock(session, pot.id)
    event = await pot_ownership_repository.get_by_id(session, pot.id, event_id)
    if event is None:
        raise NotFoundError("Ownership event not found")
    if not _may_delete_event(event, viewer.id, may_write=pot_service.may_write(permission)):
        # Which refusal, from the row's own state: a confirmed re-agreement is locked against everybody
        # and says so with the one way out, while everything else is the plain write-access answer.
        raise PotReagreementConfirmedError() if event.confirmed_at is not None else PotWriteRequiredError()
    # Everything the announcement and the audit entry need is read off the event BEFORE it goes, so
    # neither depends on an object whose row no longer exists.
    entry_id, entry_type = event.id, event.type
    members_by_id = {member.id: member for member in await group_repository.list_members(session, pot.group_id)}
    subject = members_by_id.get(event.member_id)
    counterparty = members_by_id.get(event.counterparty_member_id) if event.counterparty_member_id is not None else None
    if entry_type == OwnershipEventType.opening:
        deleted = await pot_ownership_repository.delete_openings(session, pot.id)
    else:
        await pot_ownership_repository.delete(session, event)
        deleted = 1
    await _audit(
        session,
        pot,
        user,
        AuditAction.deleted,
        event_id=entry_id,
        variant=entry_type,
        member=subject.display_name if subject is not None else None,
        counterparty=counterparty.display_name if counterparty is not None else None,
    )
    recipients = await _pot_audience(session, pot, user)
    group = await group_repository.get_by_id(session, pot.group_id)
    await session.commit()

    # EVERY deletion is announced, not only the counterparty's, and widening it here rather than in the
    # remedy alone is the point: until now a pot's writer could delete an opening or a contribution and
    # every percentage on the page would change with nobody told. Undoing an act is as much a change to
    # what people own as making it was, and whoever recorded the original has to learn it was undone or
    # they go on believing a split that no longer holds.
    #
    # It reuses ownership_changed with a `deleted` variant rather than earning an event of its own, so
    # somebody who has switched pot-ownership news off stays switched off for the undo too.
    #
    # It deliberately does NOT name which KIND of entry went, and the copy is the reason: the four event
    # types have names on the web and nowhere else, so an email or a push saying "removed a withdrawal"
    # would need a second vocabulary of them in both locales — four names across three channels, for a
    # sentence whose job is to say something changed and take the reader to the ledger, which states
    # exactly what. The audit entry beside it DOES record the type, for the surface that can read it.
    await notification_service.dispatch(
        NotificationEvent.ownership_changed,
        recipients,
        _pot_payload(pot, group, {"variant": "deleted", "actor": viewer.display_name}),
    )
    return deleted
