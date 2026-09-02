# The math the flow half rests on: dividing one shared amount between several people, deriving what
# each of them is owed, and turning that into the fewest payments that clear it.
#
# Named for the FLOW rather than for expenses because only one function here is about expenses. The
# division, the settle-up minimiser and the overpay waterfall are the same math whichever direction
# the money went, and shared income uses every one of them.
#
# Everything here is pure — no session, no models — so the rules can be tested exhaustively without a
# database, the way the unit accounting in `pot.py` is.
#
# Three properties hold across all of it and are the reason it looks the way it does:
#
#   * A split ALWAYS sums to the flow's total, in every method, after rounding. That is what makes
#     the balances sum to zero, so it is enforced by construction here rather than checked later.
#
#   * A member's position in a flow is TWO figures, not one. For an expense: what they consumed
#     (`amount`) and what they fronted (`paid_amount`). For income: what they are entitled to
#     (`amount`) and what they actually received (`received_amount`). Their balance is the difference
#     either way. One pair of columns covers a member paying for the group, a shared account paying
#     for the group, a shared account paying for one member, and the mirror of all three on the way
#     in — with no special case anywhere, because neither "who fronted it" nor "who received it" is
#     always a single person, and a payer or receiver column could not say so.
#
#   * Balances NEVER net across currencies. Each currency is its own bucket, its own settle line, and
#     its own zero-sum. Owing dollars while being owed pesos is a real, common state.

from dataclasses import dataclass
from decimal import Decimal

from app.domain.errors import (
    SharedSplitNoParticipantsError,
    SharedSplitPercentagesError,
    SharedSplitSharesError,
    SharedSplitTotalError,
)
from app.domain.money import MONEY_PLACES, ONE_HUNDRED, quantize, spread_remainder
from app.models.group_money_settings import SplitMethod

ZERO = Decimal(0)


# One member's line in a split as the request states it: the seat, plus the figure that method needs.
# `figure` is unused by `equal`, an amount for `exact`, a weight for `shares`, and a percentage for
# `percentage` — one field rather than three, because exactly one is ever meaningful and three would
# create states where two are set.
@dataclass(frozen=True)
class SplitEntry:
    member_id: int
    figure: Decimal | None = None


# Who owes whom, and how much, in one currency. The output of the settle-up minimiser.
@dataclass(frozen=True)
class SettleTransfer:
    from_member_id: int
    to_member_id: int
    amount: Decimal


# Divides `total` between the entries by the given method, returning {member_id: share}.
#
# The result sums to `total` EXACTLY in every method — the rounding remainder is spread one cent at a
# time (see spread_remainder) rather than left to fall where it may, because a split that does not add
# up is a balance that does not reach zero.
#
# Each method's refusal is its own error rather than a shared "invalid split", because each names a
# different thing the user has to fix: amounts that do not add up, percentages that do not reach 100,
# or weights that are all zero.
def compute_shares(total: Decimal, method: SplitMethod, entries: list[SplitEntry]) -> dict[int, Decimal]:
    if not entries:
        raise SharedSplitNoParticipantsError()
    if method == SplitMethod.equal:
        return _split_by_weight(total, {entry.member_id: Decimal(1) for entry in entries})
    if method == SplitMethod.exact:
        return _split_exact(total, entries)
    if method == SplitMethod.percentage:
        return _split_by_percentage(total, entries)
    return _split_by_shares(total, entries)


# Exact amounts are taken as given and must already sum to the total — there is nothing to round and
# nothing to distribute, so a mismatch is refused rather than silently absorbed. A missing figure
# reads as zero: a participant explicitly given nothing is legal (it is how a payer who took no part
# is expressed), an unstated one is the same thing.
def _split_exact(total: Decimal, entries: list[SplitEntry]) -> dict[int, Decimal]:
    shares = {entry.member_id: quantize(entry.figure or ZERO, MONEY_PLACES) for entry in entries}
    stated = sum(shares.values(), ZERO)
    if stated != quantize(total, MONEY_PLACES):
        raise SharedSplitTotalError(stated, quantize(total, MONEY_PLACES))
    return shares


# Percentages must total exactly 100 — never rescaled, for the same reason a pot's opening split is
# not: quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it.
def _split_by_percentage(total: Decimal, entries: list[SplitEntry]) -> dict[int, Decimal]:
    percentages = {entry.member_id: quantize(entry.figure or ZERO, MONEY_PLACES) for entry in entries}
    stated = sum(percentages.values(), ZERO)
    if stated != ONE_HUNDRED:
        raise SharedSplitPercentagesError(stated)
    return _split_by_weight(total, percentages)


# Shares are relative weights ("two parts to one"), so unlike percentages they carry no target to hit —
# only the requirement that they are not all zero, which would leave nothing to divide by.
def _split_by_shares(total: Decimal, entries: list[SplitEntry]) -> dict[int, Decimal]:
    weights = {entry.member_id: entry.figure or ZERO for entry in entries}
    if any(weight < ZERO for weight in weights.values()):
        raise SharedSplitSharesError()
    if sum(weights.values(), ZERO) <= ZERO:
        raise SharedSplitSharesError()
    return _split_by_weight(total, weights)


# The one proportional division every method above funnels into: each part is its weight's fraction of
# the total, rounded, with the remainder spread so the parts sum to the total exactly.
# `equal` is this with every weight 1, rather than a separate division, so there is one place where a
# proportional split is computed and one place where its remainder is resolved.
def _split_by_weight(total: Decimal, weights: dict[int, Decimal]) -> dict[int, Decimal]:
    outstanding = sum(weights.values(), ZERO)
    target = quantize(total, MONEY_PLACES)
    parts = {member_id: quantize(total * weight / outstanding, MONEY_PLACES) for member_id, weight in weights.items()}
    return spread_remainder(parts, target, MONEY_PLACES)


# The one accumulator both position functions below funnel into: Σ credit − Σ debit per member, with
# anyone netting to exactly zero dropped — they are square, and a row of zeros on every screen says
# nothing.
#
# Private so that neither caller can be handed the columns in the wrong order: each public function
# names its own two figures in its own terms, which is the whole reason there are two of them rather
# than one generic entry point taking a debit and a credit. A crossed pair here type-checks, produces
# balances that still sum to zero, and simply reverses who owes whom.
def _accumulate(rows: list[tuple[int, Decimal, Decimal]]) -> dict[int, Decimal]:
    positions: dict[int, Decimal] = {}
    for member_id, debit, credit in rows:
        positions[member_id] = positions.get(member_id, ZERO) + credit - debit
    return {member_id: value for member_id, value in positions.items() if value != ZERO}


# What each member is owed (positive) or owes (negative) for the group's EXPENSES in one currency,
# from the two sides of every split they hold: Σ paid_amount − Σ amount. Fronting money is a claim on
# the group; consuming what it bought is the group having already given you your part.
#
# Takes plain tuples rather than model rows so the rule stays testable without a database and so the
# repository can hand it an aggregate instead of every split. Rows are (member_id, amount,
# paid_amount) — the column order shared_expense_repository.list_positions_by_groups produces.
def expense_positions(rows: list[tuple[int, Decimal, Decimal]]) -> dict[int, Decimal]:
    return _accumulate(rows)


# The same figure for the group's INCOME: Σ amount − Σ received_amount, where `amount` is what the
# member is entitled to and `received_amount` is what actually reached them.
#
# The mirror of the expense rule rather than an unrelated one. An entitlement is a claim on the group;
# cash that has already arrived is the group having settled part of it. So somebody who collects the
# whole of a shared rent owes the others their shares, and somebody who was entitled to a share and
# got nothing is owed it — the same two directions an expense produces, in the same buckets, cleared
# by the same settlements.
#
# Rows are (member_id, amount, received_amount) — the order
# shared_income_repository.list_positions_by_groups produces, which is `amount` first in BOTH
# repositories so the two aggregates read alike even though the sign of `amount` differs between them.
def income_positions(rows: list[tuple[int, Decimal, Decimal]]) -> dict[int, Decimal]:
    return _accumulate([(member_id, received_amount, amount) for member_id, amount, received_amount in rows])


# One member-to-value map per flow, added together. A member square on expenses and owed on income is
# owed; one owed on expenses and owing the same on income is square, and is dropped here rather than
# rendered as a 0.00 nobody needs to see.
#
# Separate from the two functions above because each of them drops its own zeros: adding their outputs
# can reintroduce a zero that neither could have seen on its own.
def combine_positions(*parts: dict[int, Decimal]) -> dict[int, Decimal]:
    combined: dict[int, Decimal] = {}
    for part in parts:
        for member_id, value in part.items():
            combined[member_id] = combined.get(member_id, ZERO) + value
    return {member_id: value for member_id, value in combined.items() if value != ZERO}


# Applies recorded settlements to the positions above, in one currency.
#
# A payment moves the debt, not the money's direction: paying reduces what you owe, so the payer's
# position RISES by the amount and the payee's falls. A write-off has exactly the same arithmetic —
# the creditor gives up the claim, which lowers their position and raises the debtor's — which is why
# it lives in the same table and needs no branch here.
#
# Rows must already be filtered to the statuses that count. A pending settlement counts: the money
# really moved, and confirming it is an acknowledgement rather than a gate on arithmetic.
def apply_settlements(positions: dict[int, Decimal], rows: list[tuple[int, int, Decimal]]) -> dict[int, Decimal]:
    net = dict(positions)
    for from_member_id, to_member_id, amount in rows:
        net[from_member_id] = net.get(from_member_id, ZERO) + amount
        net[to_member_id] = net.get(to_member_id, ZERO) - amount
    return {member_id: value for member_id, value in net.items() if value != ZERO}


# The fewest payments that clear one currency's balances: match the largest debtor against the largest
# creditor, settle whichever is smaller, and repeat. A pays C directly rather than A→B→C.
#
# Deterministic: both sides are ordered by magnitude and then by member id, so the same balances always
# produce the same plan rather than one that depends on dict ordering. Greedy is not provably minimal
# for every set (that problem is NP-hard in general), but it is optimal whenever no proper subset of
# members sums to zero, which is every household-sized case, and it never produces more than n−1
# payments — the bound that matters against the naive "everyone pays everyone".
#
# Positions must already sum to zero, which they do by construction; the loop therefore terminates with
# nothing left over rather than needing a tolerance.
def minimise_transfers(positions: dict[int, Decimal]) -> list[SettleTransfer]:
    debtors = sorted(((member_id, -value) for member_id, value in positions.items() if value < ZERO), key=lambda pair: (-pair[1], pair[0]))
    creditors = sorted(((member_id, value) for member_id, value in positions.items() if value > ZERO), key=lambda pair: (-pair[1], pair[0]))
    transfers: list[SettleTransfer] = []
    debtor_index = 0
    creditor_index = 0
    owed = debtors[debtor_index][1] if debtors else ZERO
    due = creditors[creditor_index][1] if creditors else ZERO
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        moved = min(owed, due)
        transfers.append(SettleTransfer(from_member_id=debtors[debtor_index][0], to_member_id=creditors[creditor_index][0], amount=moved))
        owed -= moved
        due -= moved
        # Whichever side reached zero advances; when both do, both advance, so a pair that clears each
        # other exactly costs one payment rather than two.
        if owed == ZERO:
            debtor_index += 1
            owed = debtors[debtor_index][1] if debtor_index < len(debtors) else ZERO
        if due == ZERO:
            creditor_index += 1
            due = creditors[creditor_index][1] if creditor_index < len(creditors) else ZERO
    return transfers


# One bucket the excess from an overpayment COULD be applied to: what is still owed in it, and what
# clearing that would cost in the currency being paid.
#
# The caller resolves `cost` because only it has the rates. Carrying both figures rather than a rate
# is what keeps the allocation below pure — and the ratio between them IS the rate, so a partial
# allocation needs no rate of its own and cannot round differently from the full one.
@dataclass(frozen=True)
class WaterfallCandidate:
    currency: str
    outstanding: Decimal
    cost: Decimal


# One bucket the excess actually reaches, and by how much.
#
# `cost` is what this step consumes of the payment, in the payment's currency; `amount` is what comes
# off the bucket, in the bucket's own. They are two different currencies' worth of the same act, which
# is exactly the pair a settlement row already stores.
@dataclass(frozen=True)
class WaterfallStep:
    currency: str
    outstanding: Decimal
    amount: Decimal
    cost: Decimal


# Where an overpayment lands: the buckets it reaches, and what is left over after them.
#
# `leftover` is in the PAYMENT's currency and is a credit — money handed over that no open bucket
# absorbed. It is not an error and not rounding noise: it is what the payer is now owed, and the
# primary settlement carries it so the payment's own bucket flips by exactly that much.
@dataclass(frozen=True)
class WaterfallPlan:
    steps: list[WaterfallStep]
    leftover: Decimal


# Allocates the excess from an overpayment across the payer's other open buckets, largest first.
#
# Bounded and terminating by construction: each candidate is visited once, in a fixed order, and every
# step strictly reduces the excess. There is no recursion and no rate to re-derive per pass, which is
# what makes the plan safe to show and safe to re-run — the same inputs always produce the same plan,
# so what the payer confirmed is what gets written.
#
# ONE invariant holds over every input and is what the caller relies on: **the steps' costs plus the
# leftover equal the excess exactly.** The money handed over is fully accounted for, in the currency it
# was handed over in, however the per-bucket rounding falls. That is why a partial step's cost is the
# whole of what remains rather than a figure re-derived from its rounded amount — re-deriving would
# lose or invent minor units, and cash that does not reconcile is the one thing a settle-up screen
# cannot ship.
#
# Largest-cost first, ties broken by currency code so the plan is stable between reads. Ordering only
# decides which bucket a partial excess fills; the payer changes that by unchecking a bucket, which
# re-runs this without it.
def plan_waterfall(excess: Decimal, candidates: list[WaterfallCandidate]) -> WaterfallPlan:
    remaining = excess
    steps: list[WaterfallStep] = []
    for candidate in sorted(candidates, key=lambda entry: (-entry.cost, entry.currency)):
        if remaining <= ZERO:
            break
        if candidate.outstanding <= ZERO or candidate.cost <= ZERO:
            continue
        if candidate.cost <= remaining:
            steps.append(
                WaterfallStep(currency=candidate.currency, outstanding=candidate.outstanding, amount=candidate.outstanding, cost=candidate.cost)
            )
            remaining -= candidate.cost
            continue
        # What remains buys only part of this bucket. The share is a pure ratio of the two figures the
        # candidate already carries, so it cannot disagree with the rate that produced `cost`.
        amount = min(quantize(candidate.outstanding * remaining / candidate.cost, MONEY_PLACES), candidate.outstanding)
        # Too small to move this bucket by one minor unit. Skipped rather than ended: a cheaper bucket
        # further down the list may still be moved by the same money, because each bucket converts at
        # its own rate.
        if amount <= ZERO:
            continue
        steps.append(WaterfallStep(currency=candidate.currency, outstanding=candidate.outstanding, amount=amount, cost=remaining))
        remaining = ZERO
    return WaterfallPlan(steps=steps, leftover=remaining)
