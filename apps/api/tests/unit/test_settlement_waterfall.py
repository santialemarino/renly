from decimal import Decimal

import pytest

from app.domain.money import MONEY_PLACES, quantize
from app.domain.shared_flow import WaterfallCandidate, plan_waterfall

# Where an overpayment lands when the payer owes the payee in more than one currency.
#
# The property every test here defends, and the reason the plan is safe to show somebody before they
# hand over real money: **the steps' costs plus the leftover equal the excess, exactly.** Not to a
# tolerance — exactly, in the currency the payment was made in. A settle-up screen that loses a cent
# between what was paid and what it says was paid is worse than one that refuses to spill at all.
#
# Fixtures use rates that do NOT divide evenly (1 USD = 1,037.50 ARS rather than 1,000) because a
# round rate cannot tell a correct allocation from an incorrect one: every rounding path agrees when
# the arithmetic comes out whole.


def _candidate(currency: str, outstanding: str, cost: str) -> WaterfallCandidate:
    return WaterfallCandidate(currency=currency, outstanding=Decimal(outstanding), cost=Decimal(cost))


# The invariant, asserted the same way everywhere so a failure names it rather than an example.
def _assert_reconciles(plan, excess: Decimal) -> None:
    assert sum(step.cost for step in plan.steps) + plan.leftover == excess


class TestTheExcessIsFullyAccountedFor:
    @pytest.mark.parametrize(
        "excess",
        # Under the first bucket, exactly on it, between the two, exactly on both, over everything,
        # and a single minor unit — every boundary the loop can land on.
        ["0.01", "500.00", "1037.50", "1500.00", "3112.50", "9999.99"],
    )
    def test_the_costs_plus_the_leftover_are_the_excess(self, excess):
        plan = plan_waterfall(
            Decimal(excess),
            [_candidate("USD", "1.00", "1037.50"), _candidate("BRL", "10.00", "2075.00")],
        )
        _assert_reconciles(plan, Decimal(excess))

    def test_it_holds_when_nothing_is_reachable(self):
        # No candidates at all: the whole excess is a credit, and the sum of an empty list must not
        # quietly become something other than zero.
        plan = plan_waterfall(Decimal("500.00"), [])
        assert plan.steps == []
        assert plan.leftover == Decimal("500.00")

    def test_it_holds_when_the_excess_is_zero(self):
        plan = plan_waterfall(Decimal("0"), [_candidate("USD", "1.00", "1037.50")])
        assert plan.steps == []
        assert plan.leftover == Decimal("0")


class TestFullSteps:
    def test_a_bucket_the_excess_covers_is_cleared_whole(self):
        plan = plan_waterfall(Decimal("1037.50"), [_candidate("USD", "1.00", "1037.50")])
        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.currency == "USD"
        # The bucket's OWN currency for what comes off it, the payment's for what it cost. Reading
        # either as the other is the mistake the two fields exist to prevent.
        assert step.amount == Decimal("1.00")
        assert step.cost == Decimal("1037.50")
        assert step.outstanding == Decimal("1.00")
        assert plan.leftover == Decimal("0")

    def test_several_buckets_clear_in_turn(self):
        plan = plan_waterfall(
            Decimal("3112.50"),
            [_candidate("USD", "1.00", "1037.50"), _candidate("BRL", "10.00", "2075.00")],
        )
        assert [(step.currency, step.amount) for step in plan.steps] == [("BRL", Decimal("10.00")), ("USD", Decimal("1.00"))]
        assert plan.leftover == Decimal("0")

    def test_the_largest_cost_goes_first(self):
        """Ordering, not merely membership.

        A sweep survives on the sort: with both buckets fully covered every sum-based assertion stays
        green while the steps come out in input order. It only shows when the excess covers ONE of
        them, which is the case below — the larger bucket has to be the one that gets it.
        """
        plan = plan_waterfall(
            Decimal("2075.00"),
            [_candidate("USD", "1.00", "1037.50"), _candidate("BRL", "10.00", "2075.00")],
        )
        assert [step.currency for step in plan.steps] == ["BRL"]

    def test_ties_break_on_the_currency_code_so_the_plan_is_stable(self):
        first = plan_waterfall(Decimal("1037.50"), [_candidate("USD", "1.00", "1037.50"), _candidate("EUR", "0.90", "1037.50")])
        second = plan_waterfall(Decimal("1037.50"), [_candidate("EUR", "0.90", "1037.50"), _candidate("USD", "1.00", "1037.50")])
        assert [step.currency for step in first.steps] == [step.currency for step in second.steps] == ["EUR"]


class TestPartialSteps:
    def test_a_partial_step_takes_the_whole_of_what_remains(self):
        # 500 of a 1,037.50 bucket buys 500/1037.50 = 0.4819... of one dollar → 0.48.
        plan = plan_waterfall(Decimal("500.00"), [_candidate("USD", "1.00", "1037.50")])
        step = plan.steps[0]
        assert step.amount == Decimal("0.48")
        # The cost is what was actually handed over, NOT a figure re-derived from the rounded amount.
        # Re-deriving would give 0.48 × 1037.50 = 498.00 and lose two pesos that really moved.
        assert step.cost == Decimal("500.00")
        assert plan.leftover == Decimal("0")
        _assert_reconciles(plan, Decimal("500.00"))

    def test_an_excess_too_small_to_move_a_bucket_skips_it(self):
        # One peso against a bucket of a thousand dollars buys 0.0000009 of a dollar — nothing.
        plan = plan_waterfall(Decimal("0.01"), [_candidate("USD", "1000.00", "1037500.00")])
        assert plan.steps == []
        assert plan.leftover == Decimal("0.01")

    def test_a_bucket_too_expensive_to_move_does_not_stop_a_cheaper_one(self):
        """The `continue` rather than a `break`, and it is not a stylistic choice.

        Each bucket converts at its OWN rate, so money that cannot buy one minor unit of an expensive
        bucket may still buy one of a cheaper bucket further down the list. Breaking out of the loop
        would strand the excess as a credit while an open bucket it could have cleared sat right there.
        """
        plan = plan_waterfall(
            Decimal("0.60"),
            # Ordered so the unreachable one is visited FIRST: a thousand dollars at ~1,037 a piece,
            # then a bucket denominated in a currency worth about half a peso.
            [_candidate("USD", "1000.00", "1037500.00"), _candidate("CLP", "2.00", "1.00")],
        )
        assert [step.currency for step in plan.steps] == ["CLP"]
        assert plan.steps[0].amount == Decimal("1.20")
        _assert_reconciles(plan, Decimal("0.60"))

    def test_rounding_never_clears_more_of_a_bucket_than_is_owed(self):
        # 1,037.49 of a 1,037.50 bucket is 0.99999... of a dollar, which rounds to 1.00 — the whole
        # bucket, for one centavo less than it costs. The min() is what stops the plan claiming to
        # clear more than the bucket holds; without it a later `outstanding - amount` goes negative.
        plan = plan_waterfall(Decimal("1037.49"), [_candidate("USD", "1.00", "1037.50")])
        assert plan.steps[0].amount == Decimal("1.00")
        assert plan.steps[0].amount <= plan.steps[0].outstanding

    def test_only_the_last_reached_bucket_is_ever_partial(self):
        plan = plan_waterfall(
            Decimal("2500.00"),
            [_candidate("USD", "1.00", "1037.50"), _candidate("BRL", "10.00", "2075.00")],
        )
        assert [step.currency for step in plan.steps] == ["BRL", "USD"]
        assert plan.steps[0].amount == plan.steps[0].outstanding
        assert plan.steps[1].amount < plan.steps[1].outstanding
        _assert_reconciles(plan, Decimal("2500.00"))


class TestDegenerateCandidates:
    @pytest.mark.parametrize(("outstanding", "cost"), [("0", "1037.50"), ("1.00", "0"), ("0", "0")])
    def test_a_bucket_with_nothing_owed_or_no_cost_is_skipped(self, outstanding, cost):
        """A zero cost would divide by zero in the partial branch.

        Unreachable through the service — a candidate is built from a settle-up suggestion, which only
        exists for a non-zero balance — but the guard is here rather than assumed, because the failure
        it prevents is a 500 on a screen about somebody's money.
        """
        plan = plan_waterfall(Decimal("500.00"), [_candidate("USD", outstanding, cost)])
        assert plan.steps == []
        assert plan.leftover == Decimal("500.00")


class TestTheAmountsAreStorableMoney:
    @pytest.mark.parametrize("excess", ["0.01", "13.37", "500.00", "1037.49", "2500.00", "3112.50"])
    def test_every_figure_is_two_decimal_places(self, excess):
        # Both figures land in NUMERIC(18,2) columns. A third decimal is not a rounding nicety here —
        # the column would silently round it, and the stored balance would stop matching the plan the
        # payer confirmed.
        plan = plan_waterfall(
            Decimal(excess),
            [_candidate("USD", "1.00", "1037.50"), _candidate("BRL", "10.00", "2075.00")],
        )
        for step in plan.steps:
            assert step.amount == quantize(step.amount, MONEY_PLACES)
            assert step.cost == quantize(step.cost, MONEY_PLACES)
        assert plan.leftover == quantize(plan.leftover, MONEY_PLACES)
