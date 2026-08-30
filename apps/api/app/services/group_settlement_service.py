# Business logic for a group's balances and the settlements that clear them.
#
# The balance model in one paragraph. Every shared expense records what each member consumed and what
# they fronted; a member's position in one currency is the difference, summed over every expense, with
# recorded settlements applied on top. Positions are DERIVED — nothing is stored as a running total,
# matching how every other balance in Renly works — and they sum to zero in each currency by
# construction rather than by a rule anyone has to remember.
#
# Balances NEVER net across currencies. Each currency is its own bucket, its own settle line and its
# own zero-sum: owing dollars while being owed pesos is a real, common state, and merging the two
# would invent a rate nobody agreed to. The converted figure beside a bucket is for reading at a
# glance and is never what anybody settles.
#
# Who may do what, and why each is a different question:
#   * anyone in the group may RECORD a settlement — either side of a payment can be the one who
#     remembers to write it down;
#   * only the PAYEE may confirm or un-confirm one, because confirming means "I received this";
#   * only the CREDITOR may write a balance off, because giving up a claim is theirs to give up;
#   * either named member may delete a PENDING settlement, which is what makes a marked-paid payment
#     reversible until it is confirmed.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    GroupBalanceOutstandingError,
    GroupSettlementBeforeAccountOpenedError,
    GroupSettlementConfirmedError,
    GroupSettlementForeignLegError,
    GroupSettlementLegAmountRequiredError,
    GroupSettlementLegAmountsMustMatchError,
    GroupSettlementLegWithoutAccountError,
    GroupSettlementNotCreditorError,
    GroupSettlementNotPayeeError,
    GroupSettlementSameMemberError,
    GroupSettlementWriteOffHasNoLegError,
    NotFoundError,
    apply_settlements,
    expense_positions,
    minimise_transfers,
)
from app.models.account import Account
from app.models.group import GroupMember
from app.models.group_settlement import GroupSettlement, GroupSettlementStatus
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import (
    account_repository,
    group_money_settings_repository,
    group_repository,
    group_settlement_repository,
    shared_expense_repository,
)
from app.schemas.group_settlement import (
    GroupBalancesResponse,
    GroupCurrencyBalanceResponse,
    GroupMemberBalanceResponse,
    GroupSettlementResponse,
    GroupSettleSuggestionResponse,
)
from app.services import exchange_rate_service, group_service
from app.utils.metrics import convert_optional

ZERO = Decimal(0)


# Every member's position per currency, plus the fewest payments that clear each bucket.
#
# Two queries produce the whole thing regardless of how many expenses a group has: the splits are
# aggregated to (currency, member, consumed, fronted) in SQL, and the settlements are read as
# (currency, from, to, amount). A group with a thousand expenses costs one row per member per bucket.
async def get_balances(session: AsyncSession, group_id: int, user: User, *, currency: str | None = None) -> GroupBalancesResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    positions = await _positions_by_currency(session, group_id)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    buckets: list[GroupCurrencyBalanceResponse] = []
    skipped: set[str] = set()
    for bucket_currency in sorted(positions):
        net = positions[bucket_currency]
        mine = net.get(viewer.id, ZERO)
        # TODAY's rate, not the date of any contributing expense: a balance is a live position, and
        # the expenses behind it have already been reduced to one figure per bucket with no single
        # date to convert at. Passing None here instead reaches `bisect` inside the rate lookup and
        # raises TypeError — a 500 on every request that asks for a display currency.
        converted = convert_optional(mine, bucket_currency, currency, lookup, date_type.today()) if mine != ZERO else None
        if currency and mine != ZERO and bucket_currency != currency and converted is None:
            skipped.add(bucket_currency)
        buckets.append(
            GroupCurrencyBalanceResponse(
                currency=bucket_currency,
                # Largest creditor first, then largest debtor last, so the list reads as a ranking
                # rather than in seat order; ties break on member id so it is stable between reads.
                balances=[
                    GroupMemberBalanceResponse(
                        member_id=member_id,
                        display_name=_display_name(members_by_id, member_id),
                        amount=amount,
                        is_self=member_id == viewer.id,
                    )
                    for member_id, amount in sorted(net.items(), key=lambda pair: (-pair[1], pair[0]))
                ],
                suggestions=[
                    GroupSettleSuggestionResponse(
                        from_member_id=transfer.from_member_id,
                        from_display_name=_display_name(members_by_id, transfer.from_member_id),
                        to_member_id=transfer.to_member_id,
                        to_display_name=_display_name(members_by_id, transfer.to_member_id),
                        amount=transfer.amount,
                    )
                    for transfer in minimise_transfers(net)
                ],
                my_balance=mine,
                my_converted_balance=converted,
            )
        )
    return GroupBalancesResponse(group_id=group_id, buckets=buckets, display_currency=currency, skipped_currencies=sorted(skipped))


# Lists a group's settlements, newest first, with both parties named and the two per-row permissions
# resolved for the caller. Resolved here rather than by the client because they follow from who the
# caller is, and a client deriving them would be a second copy of a rule the service already enforces.
async def list_settlements(session: AsyncSession, group_id: int, user: User) -> list[GroupSettlementResponse]:
    _, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    settlements = await group_settlement_repository.list_by_group(session, group_id)
    return [_build_response(settlement, members_by_id, viewer.id) for settlement in settlements]


# Records a payment one member made to another.
#
# Confirmed on the spot when the group has opted into auto-finalise, which is D28's near-zero-friction
# path for a couple. Otherwise it lands pending: it already counts against the balance — the money
# really moved — and the payee's confirmation is the acknowledgement, not a gate on the arithmetic.
async def record_settlement(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    from_member_id: int,
    to_member_id: int,
    date: date_type,
    amount: Decimal,
    currency: str,
    from_account_id: int | None = None,
    from_amount: Decimal | None = None,
    to_account_id: int | None = None,
    to_amount: Decimal | None = None,
    notes: str | None = None,
) -> GroupSettlementResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = await _require_two_seats(session, group_id, from_member_id, to_member_id)
    # Only the caller's OWN leg may be named here. The two legs belong to two different people and
    # neither can see the other's accounts — the policies hide them — so a request naming both could
    # only have guessed an id. The other side attaches theirs through set_leg.
    _ensure_own_leg(viewer, from_member_id, from_account_id, from_amount)
    _ensure_own_leg(viewer, to_member_id, to_account_id, to_amount)
    from_leg = await _resolve_leg(session, members_by_id[from_member_id], from_account_id, from_amount, amount=amount, currency=currency, date=date)
    to_leg = await _resolve_leg(session, members_by_id[to_member_id], to_account_id, to_amount, amount=amount, currency=currency, date=date)
    settings = await group_money_settings_repository.get_by_group_id(session, group_id)
    auto_finalise = settings is not None and settings.auto_finalise_settlements
    settlement = await group_settlement_repository.create(
        session,
        GroupSettlement(
            group_id=group_id,
            from_member_id=from_member_id,
            to_member_id=to_member_id,
            date=date,
            amount=amount,
            currency=currency,
            status=GroupSettlementStatus.confirmed if auto_finalise else GroupSettlementStatus.pending,
            confirmed_at=utcnow() if auto_finalise else None,
            from_account_id=from_account_id,
            from_amount=from_leg,
            to_account_id=to_account_id,
            to_amount=to_leg,
            notes=notes,
        ),
    )
    settlement.created_by = user.id
    await session.commit()
    await session.refresh(settlement)
    return _build_response(settlement, members_by_id, viewer.id)


# Records a debt the creditor has given up on. It clears the same bucket a payment would and moves no
# money, so it names no account and carries no cash leg.
#
# Only the creditor may record one: writing off is giving up a claim, and a debtor writing off their
# own debt would be deciding on somebody else's behalf. The creditor is `to_member_id` — the seat that
# would have received the payment.
async def record_write_off(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    from_member_id: int,
    to_member_id: int,
    date: date_type,
    amount: Decimal,
    currency: str,
    notes: str | None = None,
) -> GroupSettlementResponse:
    _, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = await _require_two_seats(session, group_id, from_member_id, to_member_id)
    if viewer.id != to_member_id:
        raise GroupSettlementNotCreditorError()
    settlement = await group_settlement_repository.create(
        session,
        GroupSettlement(
            group_id=group_id,
            from_member_id=from_member_id,
            to_member_id=to_member_id,
            date=date,
            amount=amount,
            currency=currency,
            status=GroupSettlementStatus.written_off,
            notes=notes,
        ),
    )
    settlement.created_by = user.id
    await session.commit()
    await session.refresh(settlement)
    return _build_response(settlement, members_by_id, viewer.id)


# Marks a pending settlement as received. Only the payee may — it is the trust anchor for real money,
# and it means "I got this".
async def confirm_settlement(session: AsyncSession, group_id: int, settlement_id: int, user: User) -> GroupSettlementResponse:
    settlement, members_by_id, viewer = await _require_settlement(session, group_id, settlement_id, user)
    if settlement.status != GroupSettlementStatus.pending:
        raise GroupSettlementConfirmedError()
    _ensure_payee(settlement, viewer)
    settlement.status = GroupSettlementStatus.confirmed
    settlement.confirmed_at = utcnow()
    await group_settlement_repository.save(session, settlement)
    await session.commit()
    await session.refresh(settlement)
    return _build_response(settlement, members_by_id, viewer.id)


# Takes back a confirmation, returning the settlement to pending so it can be corrected or deleted.
# Only the payee may, for the same reason only they may confirm: it is their word being withdrawn.
async def unconfirm_settlement(session: AsyncSession, group_id: int, settlement_id: int, user: User) -> GroupSettlementResponse:
    settlement, members_by_id, viewer = await _require_settlement(session, group_id, settlement_id, user)
    if settlement.status != GroupSettlementStatus.confirmed:
        raise NotFoundError("Settlement not found")
    _ensure_payee(settlement, viewer)
    settlement.status = GroupSettlementStatus.pending
    settlement.confirmed_at = None
    await group_settlement_repository.save(session, settlement)
    await session.commit()
    await session.refresh(settlement)
    return _build_response(settlement, members_by_id, viewer.id)


# Attaches (or clears) the caller's OWN cash leg on a settlement.
#
# It exists because the two legs belong to two different people. A settlement is one shared row, but
# "which of my accounts this moved through" is a fact only its owner has — and only its owner can even
# see the account, since the row-level policies hide everyone else's. So each side states their own,
# whenever they get to it: the payer usually at the moment they record the payment, the payee at the
# moment they confirm receiving it.
#
# Allowed in any status except a write-off, which moved no money at all. A confirmed settlement is not
# locked against this the way it is against deletion: the amount cleared and the fact of the payment
# are what confirmation vouches for, and neither changes here — only which of the caller's own
# accounts it passed through, which is theirs to state and affects nobody else's balance.
async def set_leg(
    session: AsyncSession,
    group_id: int,
    settlement_id: int,
    user: User,
    *,
    account_id: int | None,
    leg_amount: Decimal | None = None,
) -> GroupSettlementResponse:
    settlement, members_by_id, viewer = await _require_settlement(session, group_id, settlement_id, user)
    if settlement.status == GroupSettlementStatus.written_off:
        raise GroupSettlementWriteOffHasNoLegError()
    if viewer.id not in (settlement.from_member_id, settlement.to_member_id):
        raise GroupSettlementForeignLegError()
    outgoing = viewer.id == settlement.from_member_id
    resolved = await _resolve_leg(
        session,
        viewer,
        account_id,
        leg_amount,
        amount=settlement.amount,
        currency=settlement.currency,
        date=settlement.date,
    )
    if outgoing:
        settlement.from_account_id = account_id
        settlement.from_amount = resolved
    else:
        settlement.to_account_id = account_id
        settlement.to_amount = resolved
    await group_settlement_repository.save(session, settlement)
    await session.commit()
    await session.refresh(settlement)
    return _build_response(settlement, members_by_id, viewer.id)


# Removes a settlement. This IS reversing one: there is no reversed state to read back until the audit
# log exists, so the honest post-reversal state is that the payment was never recorded.
#
# A CONFIRMED settlement cannot be removed, by anyone — the payee said they received the money, and
# undoing that silently would overwrite somebody else's word. They un-confirm it first, which is a
# deliberate second act.
async def delete_settlement(session: AsyncSession, group_id: int, settlement_id: int, user: User) -> None:
    settlement, _, viewer = await _require_settlement(session, group_id, settlement_id, user)
    if settlement.status == GroupSettlementStatus.confirmed:
        raise GroupSettlementConfirmedError()
    if not _may_delete(settlement, viewer.id):
        raise GroupSettlementNotCreditorError() if settlement.status == GroupSettlementStatus.written_off else GroupSettlementNotPayeeError()
    await group_settlement_repository.delete(session, settlement)
    await session.commit()


# Refuses an operation that would strand an open balance — removing a seat, or deleting the account
# behind it. The balance is real money between real people, so it has to be settled or explicitly
# written off first; discarding it silently would take one side's claim away with neither agreeing.
#
# Takes the seats rather than the user so both callers can use it: account deletion resolves every seat
# the account holds, and member removal resolves the one being removed.
async def ensure_no_outstanding_balance(session: AsyncSession, members: list[GroupMember]) -> None:
    if not members:
        return
    group_ids = sorted({member.group_id for member in members})
    positions = await _positions_by_group(session, group_ids)
    names = {group.id: group.name for group in await group_repository.get_by_ids(session, group_ids)}
    outstanding = [
        names.get(member.group_id, str(member.group_id))
        for member in members
        if any(net.get(member.id, ZERO) != ZERO for net in positions.get(member.group_id, {}).values())
    ]
    if outstanding:
        raise GroupBalanceOutstandingError(outstanding)


# --- Internal ---


# One group's positions, keyed by currency then seat.
#
# Delegates to the batched form with a single id rather than running its own pair of queries: the
# balances endpoint, the settle-up plan and the removal guard all read this, and two derivations of
# "what does this member owe" is two things that can disagree about whether somebody is square.
async def _positions_by_currency(session: AsyncSession, group_id: int) -> dict[str, dict[int, Decimal]]:
    return (await _positions_by_group(session, [group_id])).get(group_id, {})


# Every member's position across SEVERAL groups at once, keyed by group, then currency, then seat.
#
# Two queries for the whole set regardless of how many groups or expenses are involved — which is why
# the guard that runs before an account is deleted takes the seats in one call rather than asking per
# group inside a loop.
async def _positions_by_group(session: AsyncSession, group_ids: list[int]) -> dict[int, dict[str, dict[int, Decimal]]]:
    rows = await shared_expense_repository.list_positions_by_groups(session, group_ids)
    movements = await group_settlement_repository.list_movements_by_groups(session, group_ids)
    consumed: dict[tuple[int, str], list[tuple[int, Decimal, Decimal]]] = {}
    for group_id, currency, member_id, amount, paid_amount in rows:
        consumed.setdefault((group_id, currency), []).append((member_id, amount, paid_amount))
    settled: dict[tuple[int, str], list[tuple[int, int, Decimal]]] = {}
    for group_id, currency, from_member_id, to_member_id, amount in movements:
        settled.setdefault((group_id, currency), []).append((from_member_id, to_member_id, amount))
    positions: dict[int, dict[str, dict[int, Decimal]]] = {}
    for key in set(consumed) | set(settled):
        group_id, currency = key
        net = apply_settlements(expense_positions(consumed.get(key, [])), settled.get(key, []))
        if net:
            positions.setdefault(group_id, {})[currency] = net
    return positions


# Loads a settlement, the group's roster and the caller's seat, or raises NotFoundError. The
# settlement's own group is what membership is checked against, so an id from another group answers 404.
async def _require_settlement(
    session: AsyncSession, group_id: int, settlement_id: int, user: User
) -> tuple[GroupSettlement, dict[int, GroupMember], GroupMember]:
    _, viewer = await group_service.require_member(session, group_id, user)
    settlement = await group_settlement_repository.get_by_id(session, settlement_id)
    if settlement is None or settlement.group_id != group_id:
        raise NotFoundError("Settlement not found")
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    return (settlement, members_by_id, viewer)


# Resolves the two seats a settlement names and refuses anything that is not an ACTIVE seat of this
# group, or the same seat twice — which would move one balance in two directions and clear nothing.
async def _require_two_seats(session: AsyncSession, group_id: int, from_member_id: int, to_member_id: int) -> dict[int, GroupMember]:
    if from_member_id == to_member_id:
        raise GroupSettlementSameMemberError()
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    for member_id in (from_member_id, to_member_id):
        member = members_by_id.get(member_id)
        if member is None or not member.is_active:
            raise NotFoundError("Group member not found")
    return members_by_id


# Validates one cash leg and returns the figure to store, which is None whenever the account moved
# exactly what the bucket cleared.
#
# Storing None for a same-currency leg is not a shortcut: every reader treats "a leg amount is set" as
# "this settlement crossed currencies", and the balance sums read coalesce(leg, amount) — so a second
# copy of the same figure would be a second thing to keep in step for no gain.
async def _resolve_leg(
    session: AsyncSession,
    member: GroupMember,
    account_id: int | None,
    leg_amount: Decimal | None,
    *,
    amount: Decimal,
    currency: str,
    date: date_type,
) -> Decimal | None:
    if account_id is None:
        if leg_amount is not None:
            raise GroupSettlementLegWithoutAccountError()
        return None
    account = await _load_own_account(session, member, account_id)
    _ensure_account_open(account, date)
    if account.currency == currency:
        # No conversion happened, so the account moved exactly what came off the bucket. A different
        # figure is refused rather than quietly preferred — it would be a bank fee inflating a payment.
        if leg_amount is not None and leg_amount != amount:
            raise GroupSettlementLegAmountsMustMatchError()
        return None
    if leg_amount is None:
        raise GroupSettlementLegAmountRequiredError(account.currency, currency)
    return leg_amount


# Refuses a leg named on the OTHER party's side of the settlement. Separate from the ownership check
# below because it is a different mistake with a different fix: that one catches an account that is not
# yours, this one catches you filling in somebody else's half of the form.
def _ensure_own_leg(viewer: GroupMember, member_id: int, account_id: int | None, leg_amount: Decimal | None) -> None:
    if (account_id is not None or leg_amount is not None) and member_id != viewer.id:
        raise GroupSettlementForeignLegError()


# A settlement leg may only name the member's OWN account, or one person could move money through
# another's. A name-only seat has no linked account at all, which this refuses without a special case.
async def _load_own_account(session: AsyncSession, member: GroupMember, account_id: int) -> Account:
    account = await account_repository.get_by_id(session, account_id, member.user_id) if member.user_id is not None else None
    if account is None:
        raise NotFoundError("Account not found")
    return account


# Each leg of the balance union is bounded below by its own account's opening_date, so a settlement
# dated earlier would clear a balance while the account it moved through never changes.
def _ensure_account_open(account: Account, date: date_type) -> None:
    if date < account.opening_date:
        raise GroupSettlementBeforeAccountOpenedError(account.opening_date)


# Confirming and un-confirming are the payee's alone.
def _ensure_payee(settlement: GroupSettlement, viewer: GroupMember) -> None:
    if settlement.to_member_id != viewer.id:
        raise GroupSettlementNotPayeeError()


# Who may remove a row: either party while a payment is pending, and only the creditor for a write-off
# — taking back a forgiveness is the creditor's to take back, exactly as giving it was.
def _may_delete(settlement: GroupSettlement, viewer_member_id: int) -> bool:
    if settlement.status == GroupSettlementStatus.written_off:
        return settlement.to_member_id == viewer_member_id
    return viewer_member_id in (settlement.from_member_id, settlement.to_member_id)


# A seat's label, falling back rather than raising — a response that failed because one roster row was
# missing would hide the money too.
def _display_name(members_by_id: dict[int, GroupMember], member_id: int) -> str:
    member = members_by_id.get(member_id)
    return member.display_name if member is not None else "—"


# Builds one settlement response with both parties named and the caller's two permissions resolved.
def _build_response(settlement: GroupSettlement, members_by_id: dict[int, GroupMember], viewer_member_id: int) -> GroupSettlementResponse:
    return GroupSettlementResponse(
        id=settlement.id,
        group_id=settlement.group_id,
        from_member_id=settlement.from_member_id,
        from_display_name=_display_name(members_by_id, settlement.from_member_id),
        to_member_id=settlement.to_member_id,
        to_display_name=_display_name(members_by_id, settlement.to_member_id),
        date=settlement.date,
        amount=settlement.amount,
        currency=settlement.currency,
        status=settlement.status,
        from_account_id=settlement.from_account_id,
        from_amount=settlement.from_amount,
        to_account_id=settlement.to_account_id,
        to_amount=settlement.to_amount,
        confirmed_at=settlement.confirmed_at,
        notes=settlement.notes,
        can_confirm=settlement.status == GroupSettlementStatus.pending and settlement.to_member_id == viewer_member_id,
        can_delete=settlement.status != GroupSettlementStatus.confirmed and _may_delete(settlement, viewer_member_id),
        created_at=settlement.created_at,
        updated_at=settlement.updated_at,
    )
