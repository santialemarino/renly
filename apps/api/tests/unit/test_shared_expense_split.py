from decimal import Decimal

import pytest

from app.domain.errors import (
    SharedExpenseNoParticipantsError,
    SharedExpensePercentagesError,
    SharedExpenseSharesError,
    SharedExpenseSplitTotalError,
)
from app.domain.money import MONEY_PLACES, quantize, spread_remainder
from app.domain.shared_expense import SplitEntry, apply_settlements, compute_shares, expense_positions, minimise_transfers
from app.models.group_money_settings import SplitMethod

# The split math, and the one property the whole flow half rests on: every method's parts sum to the
# expense's total EXACTLY, so the group's balances sum to zero. A split that does not add up is a
# balance that never reaches zero, and nothing downstream would say so.


def _entries(*pairs) -> list[SplitEntry]:
    return [SplitEntry(member_id=member_id, figure=None if figure is None else Decimal(str(figure))) for member_id, figure in pairs]


class TestEqualSplit:
    @pytest.mark.parametrize(
        ("total", "count"),
        # 10/3 leaves a cent over; 10/6 rounds UP past the total and has to give two back; 100/7 gives
        # three back. All three directions of remainder, on figures a person would actually enter.
        [("10.00", 3), ("10.00", 6), ("100.00", 7), ("0.01", 3), ("33.33", 2), ("1000000.00", 9)],
    )
    def test_the_parts_always_sum_to_the_total(self, total, count):
        shares = compute_shares(Decimal(total), SplitMethod.equal, _entries(*[(i, None) for i in range(1, count + 1)]))
        assert sum(shares.values()) == Decimal(total)

    def test_the_remainder_lands_on_the_largest_parts_first(self):
        """WHICH member absorbs it, not merely how much.

        A mutation sweep survived on the ordering: dropping the sort still hands out the right NUMBER
        of cents, so every sum-based assertion stays green while the money moves to different people.
        A weighted split is what shows it — in an equal one every part is the same and the two orders
        coincide, which is why the case below is 2:1:1 rather than three ways.
        """
        # 10.00 over weights 2:1:1 is 5.00 / 2.50 / 2.50 exactly, so nudge it: 10.01 leaves one cent
        # over and it belongs to the largest part, not to whoever happened to be listed first.
        shares = compute_shares(Decimal("10.01"), SplitMethod.shares, _entries((3, 1), (1, 2), (2, 1)))
        assert sum(shares.values()) == Decimal("10.01")
        assert shares[1] == max(shares.values())
        assert shares[1] == Decimal("5.01")

    def test_equal_parts_break_the_tie_on_the_lowest_member_id(self):
        # Deterministic rather than dict-ordered: the same split always produces the same figures, so
        # a re-read never quietly moves a cent between two people.
        first = compute_shares(Decimal("10.00"), SplitMethod.equal, _entries((7, None), (3, None), (5, None)))
        assert first[3] == Decimal("3.34")
        assert first == compute_shares(Decimal("10.00"), SplitMethod.equal, _entries((5, None), (7, None), (3, None)))

    def test_no_member_carries_more_than_one_cent_of_the_remainder(self):
        # The rounding is spread one minor unit at a time rather than dumped on one member, because a
        # split amount is money somebody owes and it accumulates across every expense a group records.
        shares = compute_shares(Decimal("100.00"), SplitMethod.equal, _entries(*[(i, None) for i in range(1, 8)]))
        assert sorted(set(shares.values())) == [Decimal("14.28"), Decimal("14.29")]

    def test_an_even_division_leaves_nothing_to_spread(self):
        shares = compute_shares(Decimal("90.00"), SplitMethod.equal, _entries((1, None), (2, None), (3, None)))
        assert shares == {1: Decimal("30.00"), 2: Decimal("30.00"), 3: Decimal("30.00")}

    def test_one_participant_takes_the_whole_thing(self):
        # This is the shape the private-expense-from-a-shared-account case produces, so it is not an
        # edge case: one member consumed all of it and the money came from somewhere else.
        assert compute_shares(Decimal("48.30"), SplitMethod.equal, _entries((4, None))) == {4: Decimal("48.30")}

    def test_nobody_at_all_is_refused(self):
        with pytest.raises(SharedExpenseNoParticipantsError):
            compute_shares(Decimal("10.00"), SplitMethod.equal, [])


class TestExactSplit:
    def test_amounts_are_taken_as_given(self):
        shares = compute_shares(Decimal("10.00"), SplitMethod.exact, _entries((1, "7.50"), (2, "2.50")))
        assert shares == {1: Decimal("7.50"), 2: Decimal("2.50")}

    def test_a_zero_share_is_legal(self):
        # A payer who took no part still holds a position in the expense (D33), and this is how the
        # request says so.
        assert compute_shares(Decimal("10.00"), SplitMethod.exact, _entries((1, "10.00"), (2, "0"))) == {1: Decimal("10.00"), 2: Decimal("0.00")}

    @pytest.mark.parametrize("figures", [("7.50", "2.49"), ("7.50", "2.51"), ("10.00", "0.01")])
    def test_amounts_that_do_not_add_up_are_refused(self, figures):
        # Nothing to round and nothing to distribute — absorbing the difference onto somebody would be
        # the app deciding who pays the extra cent.
        with pytest.raises(SharedExpenseSplitTotalError) as exc:
            compute_shares(Decimal("10.00"), SplitMethod.exact, _entries((1, figures[0]), (2, figures[1])))
        assert exc.value.expected == Decimal("10.00")


class TestPercentageSplit:
    def test_percentages_divide_the_total(self):
        shares = compute_shares(Decimal("100.00"), SplitMethod.percentage, _entries((1, 90), (2, 5), (3, 5)))
        assert shares == {1: Decimal("90.00"), 2: Decimal("5.00"), 3: Decimal("5.00")}

    def test_an_awkward_percentage_still_sums_to_the_total(self):
        shares = compute_shares(Decimal("100.00"), SplitMethod.percentage, _entries((1, "33.33"), (2, "33.33"), (3, "33.34")))
        assert sum(shares.values()) == Decimal("100.00")

    @pytest.mark.parametrize("figures", [(90, 5), (90, 15), (50, 50, 1)])
    def test_percentages_that_miss_100_are_refused(self, figures):
        # Never rescaled: quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it.
        with pytest.raises(SharedExpensePercentagesError):
            compute_shares(Decimal("100.00"), SplitMethod.percentage, _entries(*[(i + 1, f) for i, f in enumerate(figures)]))


class TestSharesSplit:
    def test_weights_divide_proportionally(self):
        assert compute_shares(Decimal("30.00"), SplitMethod.shares, _entries((1, 2), (2, 1))) == {1: Decimal("20.00"), 2: Decimal("10.00")}

    def test_weights_need_no_total(self):
        # Unlike percentages, shares are relative — 4:2 is the same split as 2:1.
        assert compute_shares(Decimal("30.00"), SplitMethod.shares, _entries((1, 4), (2, 2))) == {1: Decimal("20.00"), 2: Decimal("10.00")}

    def test_an_indivisible_weighting_still_sums_to_the_total(self):
        shares = compute_shares(Decimal("10.00"), SplitMethod.shares, _entries((1, 2), (2, 1)))
        assert sum(shares.values()) == Decimal("10.00")

    @pytest.mark.parametrize("figures", [(0, 0), (None, None), (0, None)])
    def test_all_zero_weights_are_refused(self, figures):
        with pytest.raises(SharedExpenseSharesError):
            compute_shares(Decimal("10.00"), SplitMethod.shares, _entries((1, figures[0]), (2, figures[1])))

    def test_a_negative_weight_is_refused(self):
        # It would hand one member a share of less than nothing while the parts still summed to the
        # total, inverting who owes whom.
        with pytest.raises(SharedExpenseSharesError):
            compute_shares(Decimal("10.00"), SplitMethod.shares, _entries((1, 3), (2, -1)))


class TestPositionsAndSettlements:
    def test_a_position_is_what_you_fronted_minus_what_you_used(self):
        # One member pays 90 for a three-way split: they are owed 60 and each of the others owes 30.
        positions = expense_positions([(1, Decimal("30"), Decimal("90")), (2, Decimal("30"), Decimal("0")), (3, Decimal("30"), Decimal("0"))])
        assert positions == {1: Decimal("60"), 2: Decimal("-30"), 3: Decimal("-30")}

    def test_a_member_who_is_square_is_dropped(self):
        # Not the same as owning nothing: a row of zeros on every screen says nothing, and it would
        # give the settle-up plan a party with nothing to pay.
        assert expense_positions([(1, Decimal("30"), Decimal("30"))]) == {}

    def test_a_payment_moves_the_debt_in_both_directions(self):
        net = apply_settlements({1: Decimal("60"), 2: Decimal("-30"), 3: Decimal("-30")}, [(2, 1, Decimal("30"))])
        assert net == {1: Decimal("30"), 3: Decimal("-30")}

    def test_an_overpayment_flips_the_balance(self):
        # D30: an editable amount means over is the flip side of allowing partial, not a refusal.
        net = apply_settlements({1: Decimal("30"), 2: Decimal("-30")}, [(2, 1, Decimal("50"))])
        assert net == {1: Decimal("-20"), 2: Decimal("20")}

    def test_a_write_off_moves_the_same_arithmetic_as_a_payment(self):
        # The creditor gives up the claim, which lowers their position and raises the debtor's — the
        # same two lines a payment writes, which is why write-off needs no branch of its own.
        assert apply_settlements({1: Decimal("30"), 2: Decimal("-30")}, [(2, 1, Decimal("30"))]) == {}


class TestMinimisedSettleUp:
    def test_it_pays_the_creditor_directly(self):
        # D13: A pays C rather than A paying B who pays C.
        transfers = minimise_transfers({1: Decimal("-50"), 3: Decimal("30"), 4: Decimal("20")})
        assert [(t.from_member_id, t.to_member_id, t.amount) for t in transfers] == [(1, 3, Decimal("30")), (1, 4, Decimal("20"))]

    def test_a_pair_that_clears_each_other_costs_one_payment(self):
        transfers = minimise_transfers({1: Decimal("-40"), 2: Decimal("40")})
        assert len(transfers) == 1

    def test_it_never_needs_more_than_one_payment_per_member_less_one(self):
        positions = {1: Decimal("-10"), 2: Decimal("-20"), 3: Decimal("-30"), 4: Decimal("25"), 5: Decimal("35")}
        assert len(minimise_transfers(positions)) <= len(positions) - 1

    def test_the_plan_clears_the_balances_exactly(self):
        # The property that matters: applying the plan leaves nobody owing anything.
        positions = {1: Decimal("-10"), 2: Decimal("-20"), 3: Decimal("-30"), 4: Decimal("25"), 5: Decimal("35")}
        moved = [(t.from_member_id, t.to_member_id, t.amount) for t in minimise_transfers(positions)]
        assert apply_settlements(positions, moved) == {}

    def test_nothing_owed_is_no_payments(self):
        assert minimise_transfers({}) == []

    def test_the_plan_is_stable_between_reads(self):
        # Ordered by magnitude then member id, so the same balances always produce the same plan —
        # a plan that reshuffled per request would read as the app changing its mind.
        positions = {5: Decimal("-20"), 2: Decimal("20"), 9: Decimal("-20"), 7: Decimal("20")}
        first = [(t.from_member_id, t.to_member_id, t.amount) for t in minimise_transfers(positions)]
        assert first == [(t.from_member_id, t.to_member_id, t.amount) for t in minimise_transfers(dict(reversed(list(positions.items()))))]


class TestSpreadRemainder:
    def test_nothing_to_spread_returns_the_parts_untouched(self):
        parts = {1: Decimal("5.00"), 2: Decimal("5.00")}
        assert spread_remainder(parts, Decimal("10.00"), MONEY_PLACES) == parts

    def test_no_parts_at_all_is_not_a_crash(self):
        assert spread_remainder({}, Decimal("10.00"), MONEY_PLACES) == {}

    def test_a_remainder_larger_than_the_part_count_wraps(self):
        # A same-currency split cannot produce this, but a caller dividing through a rate could, and
        # silently dropping the tail would leave the parts short.
        parts = {1: quantize(Decimal("1"), MONEY_PLACES), 2: quantize(Decimal("1"), MONEY_PLACES)}
        spread = spread_remainder(parts, Decimal("2.05"), MONEY_PLACES)
        assert sum(spread.values()) == Decimal("2.05")
