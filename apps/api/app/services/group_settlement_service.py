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
    GroupSettlementLegTotalTooSmallError,
    GroupSettlementLegWithoutAccountError,
    GroupSettlementNotCreditorError,
    GroupSettlementNotPayeeError,
    GroupSettlementSameMemberError,
    GroupSettlementWriteOffHasNoLegError,
    GroupWriteOffExceedsBalanceError,
    NotFoundError,
    WaterfallCandidate,
    apply_settlements,
    expense_positions,
    minimise_transfers,
    plan_waterfall,
)
from app.domain.money import MONEY_PLACES, quantize, spread_remainder
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
    GroupSettlementPlanBucketResponse,
    GroupSettlementPlanResponse,
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


# Where a payment would land when it is bigger than the bucket it names. A dry run: writes nothing.
#
# Split from the write below rather than folded into it because the payer has to SEE this before any
# of it happens — §5's rule is that a cross-currency cascade is never silent — and because unticking a
# bucket re-asks the same question with a smaller set. Both paths call the same allocator on the same
# inputs, so what is shown is what gets written.
async def preview_waterfall(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    from_member_id: int,
    to_member_id: int,
    date: date_type,
    amount: Decimal,
    currency: str,
    spillover_currencies: list[str] | None = None,
) -> GroupSettlementPlanResponse:
    await group_service.require_member(session, group_id, user)
    await _require_two_seats(session, group_id, from_member_id, to_member_id)
    owed = await _owed_between(session, group_id, from_member_id, to_member_id)
    primary_outstanding = owed.pop(currency, ZERO)
    excess = amount - primary_outstanding
    if excess <= ZERO or not owed:
        # Not an overpayment, or nowhere for one to go. Either way there is no plan: the caller records
        # the payment the ordinary way, and an excess simply flips the bucket it was paid into.
        leftover = max(excess, ZERO)
        return GroupSettlementPlanResponse(
            currency=currency,
            amount=amount,
            primary_outstanding=primary_outstanding,
            excess=leftover,
            primary_amount=_primary_amount(amount, primary_outstanding, leftover),
            buckets=[],
            leftover=leftover,
        )
    candidates, costs, skipped = await _waterfall_candidates(session, user, owed, currency, date, spillover_currencies)
    plan = plan_waterfall(excess, candidates)
    applied = {step.currency: step for step in plan.steps}
    return GroupSettlementPlanResponse(
        currency=currency,
        amount=amount,
        primary_outstanding=primary_outstanding,
        excess=excess,
        primary_amount=_primary_amount(amount, primary_outstanding, plan.leftover),
        # Costliest first, matching the order the allocator fills them in, so the list reads top to
        # bottom as the money actually flows. Unreachable buckets keep their place rather than sinking.
        buckets=[
            GroupSettlementPlanBucketResponse(
                currency=bucket_currency,
                outstanding=owed[bucket_currency],
                cost=cost,
                amount=applied[bucket_currency].amount if bucket_currency in applied else ZERO,
                applied_cost=applied[bucket_currency].cost if bucket_currency in applied else ZERO,
                selected=spillover_currencies is None or bucket_currency in spillover_currencies,
            )
            for bucket_currency, cost in sorted(costs.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
        leftover=plan.leftover,
        skipped_currencies=sorted(skipped),
    )


# Records one payment across every bucket it reaches: one settlement per bucket, written together.
#
# The allocation is recomputed here from the same inputs the preview used, and the request carries no
# amounts for the spillover buckets at all — only which of them the payer kept. A client that could
# name those amounts could clear a bucket at a rate nobody agreed to, and the payee would have no way
# to tell from the row.
#
# One transaction. A payment that half-lands is worse than one that does not land: the payer would
# have handed money over and the balances would show part of it, with nothing saying which part.
async def record_waterfall(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    from_member_id: int,
    to_member_id: int,
    date: date_type,
    amount: Decimal,
    currency: str,
    spillover_currencies: list[str] | None = None,
    from_account_id: int | None = None,
    from_amount: Decimal | None = None,
    to_account_id: int | None = None,
    to_amount: Decimal | None = None,
    notes: str | None = None,
) -> list[GroupSettlementResponse]:
    _, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = await _require_two_seats(session, group_id, from_member_id, to_member_id)
    _ensure_own_leg(viewer, from_member_id, from_account_id, from_amount)
    _ensure_own_leg(viewer, to_member_id, to_account_id, to_amount)
    owed = await _owed_between(session, group_id, from_member_id, to_member_id)
    primary_outstanding = owed.pop(currency, ZERO)
    excess = amount - primary_outstanding
    plan = None
    if excess > ZERO and owed:
        candidates, _, _ = await _waterfall_candidates(session, user, owed, currency, date, spillover_currencies)
        plan = plan_waterfall(excess, candidates)
    steps = plan.steps if plan is not None else []
    leftover = plan.leftover if plan is not None else max(excess, ZERO)
    primary_amount = _primary_amount(amount, primary_outstanding, leftover)
    writes: list[tuple[str, Decimal, Decimal]] = []
    if primary_amount > ZERO:
        writes.append((currency, primary_amount, primary_amount))
    writes.extend((step.currency, step.amount, step.cost) for step in steps)
    # Each side's stated total is split across the rows in proportion to what each consumed of the
    # payment, and `spread_remainder` makes the parts sum to the stated total EXACTLY. Neither person's
    # account may end up moving a cent more or less than they said it did.
    #
    # Only for a side that NAMED an account. Mark-as-paid names none — the v1 default, and the only
    # thing a name-only member's side can ever be — and a figure without an account behind it is
    # refused outright, as a movement through nothing.
    #
    # Each side's account is loaded ONCE, before the loop, rather than per row: the rows differ only in
    # which bucket they clear, and re-reading the same account for each would be a query inside a loop.
    from_account = await _load_own_account(session, members_by_id[from_member_id], from_account_id) if from_account_id is not None else None
    to_account = await _load_own_account(session, members_by_id[to_member_id], to_account_id) if to_account_id is not None else None
    from_legs = _split_leg(from_amount if from_amount is not None else amount, writes, from_account.currency) if from_account is not None else {}
    to_legs = _split_leg(to_amount if to_amount is not None else amount, writes, to_account.currency) if to_account is not None else {}
    settings = await group_money_settings_repository.get_by_group_id(session, group_id)
    auto_finalise = settings is not None and settings.auto_finalise_settlements
    created: list[GroupSettlement] = []
    for index, (bucket_currency, bucket_amount, _) in enumerate(writes):
        from_leg = (
            _leg_figure(from_account, from_legs.get(index), amount=bucket_amount, currency=bucket_currency, date=date)
            if from_account is not None
            else None
        )
        to_leg = (
            _leg_figure(to_account, to_legs.get(index), amount=bucket_amount, currency=bucket_currency, date=date) if to_account is not None else None
        )
        settlement = await group_settlement_repository.create(
            session,
            GroupSettlement(
                group_id=group_id,
                from_member_id=from_member_id,
                to_member_id=to_member_id,
                date=date,
                amount=bucket_amount,
                currency=bucket_currency,
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
        created.append(settlement)
    await session.commit()
    for settlement in created:
        await session.refresh(settlement)
    return [_build_response(settlement, members_by_id, viewer.id) for settlement in created]


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
    # Capped at the balance, unlike a payment. An overpaying PAYMENT is legal and flips the bucket —
    # real money moved and the payee owes some back — but forgiving more than you are owed would leave
    # the person you forgave owing you a negative amount, which no act produces. See the error.
    outstanding = (await _owed_between(session, group_id, from_member_id, to_member_id)).get(currency, ZERO)
    if amount > outstanding:
        raise GroupWriteOffExceedsBalanceError(outstanding, currency)
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


# What one member owes another, per currency, according to the settle-up plan.
#
# Read from `minimise_transfers` rather than from the raw positions, and the difference is not
# cosmetic: a member being a net debtor in a bucket does not mean they owe THIS payee — with three
# people the minimiser is what decides who pays whom. Deriving it any other way here would be a second
# answer to that question, and the two would disagree about who the payment is even for.
#
# Only buckets where this pair actually owes in this direction are returned, so the waterfall can never
# apply money to a bucket where the payer is the one being owed.
async def _owed_between(session: AsyncSession, group_id: int, from_member_id: int, to_member_id: int) -> dict[str, Decimal]:
    positions = await _positions_by_currency(session, group_id)
    owed: dict[str, Decimal] = {}
    for currency, net in positions.items():
        for transfer in minimise_transfers(net):
            if transfer.from_member_id == from_member_id and transfer.to_member_id == to_member_id:
                owed[currency] = transfer.amount
    return owed


# Prices each open bucket in the currency being paid, so the pure allocator never needs a rate.
#
# Converted at the PAYMENT's date, not today: the rate that matters is the one in force when the money
# moved, which is how every other cross-currency figure in Renly is recorded. (`get_balances` converts
# at today's for the opposite and equally deliberate reason — a displayed balance is a live position
# with no single date behind it.)
#
# A bucket with no rate is dropped and named, never guessed at: converting at 1:1 or at a neighbouring
# day's rate would move real money at a number nobody agreed to.
async def _waterfall_candidates(
    session: AsyncSession,
    user: User,
    owed: dict[str, Decimal],
    currency: str,
    date: date_type,
    spillover_currencies: list[str] | None,
) -> tuple[list[WaterfallCandidate], dict[str, Decimal], set[str]]:
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id)
    candidates: list[WaterfallCandidate] = []
    costs: dict[str, Decimal] = {}
    skipped: set[str] = set()
    for bucket_currency, outstanding in owed.items():
        cost = convert_optional(outstanding, bucket_currency, currency, lookup, date)
        if cost is None or cost <= ZERO:
            skipped.add(bucket_currency)
            continue
        costs[bucket_currency] = cost
        if spillover_currencies is None or bucket_currency in spillover_currencies:
            candidates.append(WaterfallCandidate(currency=bucket_currency, outstanding=outstanding, cost=cost))
    return (candidates, costs, skipped)


# What the settlement against the bucket being PAID comes to.
#
# It takes whatever the payment covers of that bucket, PLUS the leftover — which is what makes the cash
# reconcile: this figure plus every step's cost is exactly what was handed over.
#
# The `min` is what keeps a partial payment honest: paying 1,000 against a 3,000 balance must record
# 1,000, not the balance. And with nothing ticked the leftover is the whole excess, so this becomes the
# single overpaying settlement — the behaviour with no waterfall at all.
#
# Zero only when the payer owed nothing in the currency they paid and every cent of it spilled, in
# which case there is no row to write against that bucket. It cannot leave a payment with no rows at
# all: with no steps the leftover is the entire amount, which is positive.
#
# ONE function, called by the preview and by the write, because the payer confirms this number and
# then it is recorded — two derivations of it would be two things that can disagree about what they
# just agreed to.
def _primary_amount(amount: Decimal, primary_outstanding: Decimal, leftover: Decimal) -> Decimal:
    return min(amount, primary_outstanding) + leftover


# Divides one side's stated cash total across the rows a payment writes, in proportion to what each
# consumed of it, summing to the stated total exactly.
#
# The proportion is over the payment's own currency, which is the only scale the rows share. It is a
# decomposition of a figure the payer actually stated rather than a conversion at a market rate — so a
# payment made at a rate their bank gave them stays recorded at that rate, across every row.
#
# With a same-currency account and no stated total this returns each row its own amount, which is what
# `_resolve_leg` then normalises back to None. One rule covers both cases rather than a branch.
def _split_leg(total: Decimal, writes: list[tuple[str, Decimal, Decimal]], account_currency: str) -> dict[int, Decimal]:
    # A row whose bucket is already in the account's own currency crosses nothing, so it moves exactly
    # what it clears — no rate is involved and none may be implied. Taking a proportional share here
    # instead would claim the account paid, say, 8.58 dollars to clear a 10-dollar bucket, which is a
    # contradiction the leg rule rightly refuses.
    fixed = {index: bucket_amount for index, (bucket_currency, bucket_amount, _) in enumerate(writes) if bucket_currency == account_currency}
    crossing = [(index, cost) for index, (bucket_currency, _, cost) in enumerate(writes) if bucket_currency != account_currency]
    crossing_cost = sum(cost for _, cost in crossing)
    if not crossing or crossing_cost <= ZERO:
        return fixed
    # What is left of the stated total after the rows that crossed nothing, split between the rest in
    # proportion to what each consumed of the payment. `spread_remainder` makes the parts sum to it
    # EXACTLY: the payer's account may not end up moving a cent more or less than they said it did.
    remainder = total - sum(fixed.values())
    # The rows that crossed nothing already account for part of the payment, one for one. A stated
    # total at or below them describes a payment that cannot have happened, and dividing what is left
    # would hand the crossing rows a zero or negative leg — refused by a DB CHECK, as a 500.
    if remainder <= ZERO:
        raise GroupSettlementLegTotalTooSmallError(sum(fixed.values()), account_currency)
    parts = {index: quantize(remainder * cost / crossing_cost, MONEY_PLACES) for index, cost in crossing}
    return {**fixed, **spread_remainder(parts, remainder, MONEY_PLACES)}


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
    return _leg_figure(account, leg_amount, amount=amount, currency=currency, date=date)


# The leg rule itself, over an account already in hand. Split from the load above so the waterfall can
# fetch each side's account ONCE and then apply this per row, rather than issuing a query inside a loop.
def _leg_figure(account: Account, leg_amount: Decimal | None, *, amount: Decimal, currency: str, date: date_type) -> Decimal | None:
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
