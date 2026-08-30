import random
from decimal import Decimal

import pytest

from app.domain.shared_expense import SplitEntry, apply_settlements, compute_shares, expense_positions, minimise_transfers
from app.models.group_money_settings import SplitMethod

# THE invariant. Whatever the splits and whatever the settlements, a group's per-currency balances sum
# to exactly zero — every peso somebody is owed is a peso somebody else owes.
#
# It is not a nice property, it is the whole feature: the settle-up plan divides the members into
# creditors and debtors and pays one set from the other, so a non-zero total means the plan cannot
# terminate and somebody is left holding money that came from nowhere. Nothing else in the system would
# say so — the figures would simply be wrong on every screen.
#
# Exhaustive rather than illustrative, because it is cheap to be: the generator below walks thousands
# of randomly-shaped groups through every split method, every funding shape (one member fronting, a
# shared account fronted by several owners in their proportions, a payer who took no part) and a random
# number of settlements on top.
#
# The seed is FIXED so a failure is reproducible; the run is not a fuzz that finds a new case each time,
# it is a fixed corpus large enough to cover the shapes by construction.
_SEED = 20260830
_CASES = 400


# One expense's split rows as the service writes them: (member_id, consumed, fronted).
def _expense_rows(rng: random.Random, member_ids: list[int]) -> list[tuple[int, Decimal, Decimal]]:
    total = Decimal(rng.randrange(1, 5_000_00)) / 100
    participants = rng.sample(member_ids, rng.randint(1, len(member_ids)))
    method = rng.choice(list(SplitMethod))
    shares = compute_shares(total, method, _figures(rng, method, participants, total))
    paid = _funding(rng, member_ids, total)
    return [(member_id, shares.get(member_id, Decimal(0)), paid.get(member_id, Decimal(0))) for member_id in sorted(set(shares) | set(paid))]


# The figures each method needs, built so the method's own precondition holds — an exact split that did
# not add up or a percentage that missed 100 would be refused, which is a different test's job.
def _figures(rng: random.Random, method: SplitMethod, participants: list[int], total: Decimal) -> list[SplitEntry]:
    if method == SplitMethod.equal:
        return [SplitEntry(member_id=member_id) for member_id in participants]
    if method == SplitMethod.shares:
        return [SplitEntry(member_id=member_id, figure=Decimal(rng.randint(1, 9))) for member_id in participants]
    if method == SplitMethod.percentage:
        parts = _partition(rng, Decimal("100"), participants)
        return [SplitEntry(member_id=member_id, figure=parts[member_id]) for member_id in participants]
    parts = _partition(rng, total, participants)
    return [SplitEntry(member_id=member_id, figure=parts[member_id]) for member_id in participants]


# Splits `target` into 2-decimal parts summing to it exactly, so exact and percentage splits are fed
# figures their own rule accepts.
def _partition(rng: random.Random, target: Decimal, members: list[int]) -> dict[int, Decimal]:
    remaining = target
    parts: dict[int, Decimal] = {}
    for member_id in members[:-1]:
        take = Decimal(rng.randrange(0, int(remaining * 100) + 1)) / 100
        parts[member_id] = take
        remaining -= take
    parts[members[-1]] = remaining
    return parts


# Who fronted the money, in the three shapes the service produces. The shared-account one is the case
# that makes this invariant non-obvious: several members front one expense in ownership proportions
# that have nothing to do with the split.
def _funding(rng: random.Random, member_ids: list[int], total: Decimal) -> dict[int, Decimal]:
    shape = rng.choice(("one_payer", "shared_account", "outsider_payer"))
    if shape == "shared_account":
        owners = rng.sample(member_ids, rng.randint(1, len(member_ids)))
        return _partition(rng, total, owners)
    return {rng.choice(member_ids): total}


class TestPositionsSumToZero:
    @pytest.mark.parametrize("case", range(_CASES))
    def test_every_generated_group_balances_to_zero(self, case):
        rng = random.Random(_SEED + case)
        member_ids = list(range(1, rng.randint(2, 7) + 1))
        rows: list[tuple[int, Decimal, Decimal]] = []
        for _ in range(rng.randint(1, 6)):
            rows.extend(_expense_rows(rng, member_ids))
        positions = expense_positions(rows)
        assert sum(positions.values(), Decimal(0)) == Decimal(0), positions

        settlements = [
            (payer, payee, Decimal(rng.randrange(1, 2_000_00)) / 100)
            for payer, payee in (rng.sample(member_ids, 2) for _ in range(rng.randint(0, 4)))
        ]
        net = apply_settlements(positions, settlements)
        assert sum(net.values(), Decimal(0)) == Decimal(0), net

        # And the plan derived from it clears the whole thing, which is what the zero-sum is FOR.
        moved = [(t.from_member_id, t.to_member_id, t.amount) for t in minimise_transfers(net)]
        assert apply_settlements(net, moved) == {}

    def test_the_generator_actually_produces_the_shapes_it_claims(self):
        # A guard on the guard. If the corpus only ever built one-payer equal splits the assertions
        # above would pass on a fraction of the system — so assert the coverage rather than assume it.
        methods: set[SplitMethod] = set()
        payer_counts: set[int] = set()
        non_participants = 0
        for case in range(_CASES):
            rng = random.Random(_SEED + case)
            member_ids = list(range(1, rng.randint(2, 7) + 1))
            for _ in range(rng.randint(1, 6)):
                total = Decimal(rng.randrange(1, 5_000_00)) / 100
                participants = rng.sample(member_ids, rng.randint(1, len(member_ids)))
                method = rng.choice(list(SplitMethod))
                methods.add(method)
                shares = compute_shares(total, method, _figures(rng, method, participants, total))
                paid = _funding(rng, member_ids, total)
                payer_counts.add(len(paid))
                non_participants += sum(1 for member_id in paid if member_id not in shares)
        assert methods == set(SplitMethod)
        assert max(payer_counts) > 1, "no shared-account expense was ever generated"
        assert non_participants > 0, "a payer who took no part was never generated"
