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
#   * Money crosses a scope boundary here and NOWHERE else. A transfer must stay within one scope
#     because it is net-worth-neutral by construction; moving joint money into a personal account is
#     not neutral for the other owners. The contribution and withdrawal mechanics are that same
#     movement recorded honestly — the private leg really is debited and the pot leg really is
#     credited, which is what makes the pot's value move with the money.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    NotFoundError,
    PotAlreadyOpenedError,
    PotBaseAmountRequiredError,
    PotInsufficientUnitsError,
    PotMovementAccountInactiveError,
    PotMovementBeforeAccountOpenedError,
    PotNotOpenedError,
    PotPercentagesError,
    PotReagreementSameMemberError,
    PotUnsupportedMovementError,
    PotValuationRequiredError,
    amount_for_units,
    opening_units,
    replay_units,
    total_units,
    unit_price,
    units_for_amount,
)
from app.domain.errors import AccountCurrencyMismatchError
from app.domain.pot import ONE_HUNDRED, OPENING_UNIT_PRICE, UNIT_PLACES, OwnershipEntry, quantize
from app.models.account import Account
from app.models.group import GroupMember
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent
from app.models.user import User
from app.repositories import account_repository, group_repository, pot_ownership_repository
from app.schemas.pot import PotOwnershipEventResponse
from app.services import exchange_rate_service, pot_service

ZERO = Decimal(0)


# Turns ledger rows into the replay entries the unit math consumes, so the domain never imports a
# model and stays testable without a database.
def _as_entries(events: list[PotOwnershipEvent]) -> list[OwnershipEntry]:
    return [OwnershipEntry(member_id=e.member_id, units=e.units, counterparty_member_id=e.counterparty_member_id) for e in events]


# Builds one ledger response, naming both members rather than exposing raw seat ids alone — a client
# rendering a movement history needs the names, and a second round trip per row to get them would be
# an N+1 pushed onto the frontend.
def _build_response(event: PotOwnershipEvent, members_by_id: dict[int, GroupMember]) -> PotOwnershipEventResponse:
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
async def _require_price(session: AsyncSession, pot: Pot, user: User, as_of_date: date_type) -> tuple[Decimal, dict[int, Decimal]]:
    events = await pot_ownership_repository.list_by_pot(session, pot.id, as_of_date=as_of_date)
    balances = replay_units(_as_entries(events))
    outstanding = total_units(balances)
    if outstanding <= 0:
        raise PotNotOpenedError()
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


# Lists a pot's ownership ledger in replay order. Visible to whoever may see the pot at all: a member
# holding 0% still sees every movement, because partial visibility of something you co-own is not a
# feature (V5).
async def list_events(session: AsyncSession, pot_id: int, user: User) -> list[PotOwnershipEventResponse]:
    pot, _, _ = await pot_service.require_visible(session, pot_id, user)
    events = await pot_ownership_repository.list_by_pot(session, pot.id)
    members = await group_repository.list_members(session, pot.group_id)
    members_by_id = {m.id: m for m in members}
    return [_build_response(e, members_by_id) for e in events]


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
    pot, _ = await pot_service.require_writable(session, pot_id, user)
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
    await session.commit()
    return [_build_response(e, members_by_id) for e in created]


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
    notes: str | None = None,
) -> PotOwnershipEventResponse:
    if type not in (OwnershipEventType.contribution, OwnershipEventType.withdrawal):
        raise PotUnsupportedMovementError(type)
    pot, _ = await pot_service.require_writable(session, pot_id, user)
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
        if units > held:
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
    await session.commit()
    return _build_response(event, {member.id: member})


# Records a re-agreement: units moving from one member to another with no money at all. Net-zero in
# units by construction — the counterparty receives exactly the negation — because this is people
# agreeing to a different split of the same pot, not value entering or leaving it.
# Taken as a PERCENTAGE of the whole pot rather than a unit count, because U2 is that percentages go
# in and percentages come out; a raw unit count appears nowhere a person can see.
async def record_reagreement(
    session: AsyncSession,
    pot_id: int,
    user: User,
    *,
    date: date_type,
    from_member_id: int,
    to_member_id: int,
    percentage: Decimal,
    notes: str | None = None,
) -> PotOwnershipEventResponse:
    pot, _ = await pot_service.require_writable(session, pot_id, user)
    giver = await _require_seat(session, pot, from_member_id)
    receiver = await _require_seat(session, pot, to_member_id)
    if giver.id == receiver.id:
        raise PotReagreementSameMemberError()
    price, balances = await _require_price(session, pot, user, date)

    outstanding = total_units(balances)
    moved = quantize(outstanding * percentage / ONE_HUNDRED, UNIT_PLACES)
    held = balances.get(giver.id, ZERO)
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
    await session.commit()
    return _build_response(event, {giver.id: giver, receiver.id: receiver})


# Deletes an ownership event. Balances are derived, so removing one recomputes the series with no
# stored total to correct — the same property that makes back-dating safe.
async def delete_event(session: AsyncSession, pot_id: int, event_id: int, user: User) -> None:
    pot, _ = await pot_service.require_writable(session, pot_id, user)
    event = await pot_ownership_repository.get_by_id(session, pot.id, event_id)
    if event is None:
        raise NotFoundError("Ownership event not found")
    await pot_ownership_repository.delete(session, event)
    await session.commit()
