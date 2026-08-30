# The math the flow half rests on: dividing one expense between several people, deriving what each of
# them is owed, and turning that into the fewest payments that clear it.
#
# Everything here is pure — no session, no models — so the rules can be tested exhaustively without a
# database, the way the unit accounting in `pot.py` is.
#
# Three properties hold across all of it and are the reason it looks the way it does:
#
#   * A split ALWAYS sums to the expense's total, in every method, after rounding. That is what makes
#     the balances sum to zero, so it is enforced by construction here rather than checked later.
#
#   * A member's position in an expense is TWO figures, not one: what they consumed (`amount`) and
#     what they fronted (`paid_amount`). Their balance is the difference. One pair of columns covers a
#     member paying for the group, a shared account paying for the group, and a shared account paying
#     for one member — with no special case anywhere, because "who fronted it" is not always a single
#     person and a payer column could not say so.
#
#   * Balances NEVER net across currencies. Each currency is its own bucket, its own settle line, and
#     its own zero-sum. Owing dollars while being owed pesos is a real, common state.

from dataclasses import dataclass
from decimal import Decimal

from app.domain.errors import (
    SharedExpenseNoParticipantsError,
    SharedExpensePercentagesError,
    SharedExpenseSharesError,
    SharedExpenseSplitTotalError,
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
        raise SharedExpenseNoParticipantsError()
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
        raise SharedExpenseSplitTotalError(stated, quantize(total, MONEY_PLACES))
    return shares


# Percentages must total exactly 100 — never rescaled, for the same reason a pot's opening split is
# not: quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it.
def _split_by_percentage(total: Decimal, entries: list[SplitEntry]) -> dict[int, Decimal]:
    percentages = {entry.member_id: quantize(entry.figure or ZERO, MONEY_PLACES) for entry in entries}
    stated = sum(percentages.values(), ZERO)
    if stated != ONE_HUNDRED:
        raise SharedExpensePercentagesError(stated)
    return _split_by_weight(total, percentages)


# Shares are relative weights ("two parts to one"), so unlike percentages they carry no target to hit —
# only the requirement that they are not all zero, which would leave nothing to divide by.
def _split_by_shares(total: Decimal, entries: list[SplitEntry]) -> dict[int, Decimal]:
    weights = {entry.member_id: entry.figure or ZERO for entry in entries}
    if any(weight < ZERO for weight in weights.values()):
        raise SharedExpenseSharesError()
    if sum(weights.values(), ZERO) <= ZERO:
        raise SharedExpenseSharesError()
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


# What each member is owed (positive) or owes (negative) in one currency, from the two sides of every
# split they hold: Σ paid_amount − Σ amount. Members whose position nets to exactly zero are dropped —
# they are square, and a row of zeros on every screen says nothing.
#
# Takes plain tuples rather than model rows so the rule stays testable without a database and so the
# repository can hand it an aggregate instead of every split.
def expense_positions(rows: list[tuple[int, Decimal, Decimal]]) -> dict[int, Decimal]:
    positions: dict[int, Decimal] = {}
    for member_id, amount, paid_amount in rows:
        positions[member_id] = positions.get(member_id, ZERO) + paid_amount - amount
    return {member_id: value for member_id, value in positions.items() if value != ZERO}


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
