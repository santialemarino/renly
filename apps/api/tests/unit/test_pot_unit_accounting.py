# Unit accounting — the math that divides a pot between its owners.
#
# Every expected value here is computed by hand and written as a literal. Calling the function under
# test to build its own expectation would assert only that it is self-consistent, which it would be
# even if the formula were wrong.

from decimal import Decimal

import pytest

from app.domain.pot import (
    OwnershipEntry,
    amount_for_units,
    opening_units,
    ownership_percentages,
    replay_units,
    share_values,
    total_units,
    unit_price,
    units_for_amount,
)


def d(value: str) -> Decimal:
    return Decimal(value)


class TestTheWorkedExample:
    # The three steps of shared-money-spec.md 5.2, asserted in order. Between them nothing but the
    # NAV changes, which is the point being demonstrated: growth is pro-rata with no event at all.
    def test_step_1_the_opening_baseline_issues_units_at_a_nominal_one(self):
        units = opening_units(d("100"), {1: d("90"), 2: d("10")})
        assert units == {1: d("90.000000"), 2: d("10.000000")}
        assert total_units(units) == d("100.000000")
        assert unit_price(d("100"), total_units(units)) == d("1.000000")
        assert share_values(units, d("100")) == {1: d("90.00"), 2: d("10.00")}

    def test_step_2_growth_is_pro_rata_with_no_event_recorded(self):
        units = {1: d("90.000000"), 2: d("10.000000")}
        # The pot grows 100 -> 110. No ledger entry exists for this, and none should.
        assert unit_price(d("110"), total_units(units)) == d("1.100000")
        assert share_values(units, d("110")) == {1: d("99.00"), 2: d("11.00")}
        # Nobody's percentage moved, because no units were issued or redeemed.
        assert ownership_percentages(units) == {1: d("90.00"), 2: d("10.00")}

    def test_step_3_a_contribution_dilutes_percentage_but_nobody_loses_value(self):
        units = {1: d("90.000000"), 2: d("10.000000")}
        price = unit_price(d("110"), total_units(units))
        # Member 2 contributes 5 at 1.10 -> 5 / 1.10 = 4.545454... -> 4.545455 at six places.
        issued = units_for_amount(d("5"), price)
        assert issued == d("4.545455")

        units[2] += issued
        assert total_units(units) == d("104.545455")

        # NAV is now 115. Member 1 still holds 90 units and is still worth 99.00 — the whole point.
        values = share_values(units, d("115"))
        assert values == {1: d("99.00"), 2: d("16.00")}
        assert sum(values.values()) == d("115.00")

        # Their percentage DID move: 90 / 104.545455 = 0.8608695... -> 86.09%.
        assert ownership_percentages(units) == {1: d("86.09"), 2: d("13.91")}


class TestReplay:
    def test_a_contribution_adds_to_the_members_balance(self):
        entries = [OwnershipEntry(1, d("90")), OwnershipEntry(2, d("10")), OwnershipEntry(2, d("4.545455"))]
        assert replay_units(entries) == {1: d("90"), 2: d("14.545455")}

    def test_a_withdrawal_is_the_same_math_with_a_negative_sign(self):
        entries = [OwnershipEntry(1, d("90")), OwnershipEntry(1, d("-15.5"))]
        assert replay_units(entries) == {1: d("74.5")}

    def test_a_reagreement_is_net_zero_in_units(self):
        entries = [OwnershipEntry(1, d("90")), OwnershipEntry(2, d("10")), OwnershipEntry(1, d("-20"), counterparty_member_id=2)]
        balances = replay_units(entries)
        assert balances == {1: d("70"), 2: d("30")}
        # The total is untouched: value moved between people, none entered or left the pot.
        assert total_units(balances) == d("100")

    def test_a_member_bought_out_completely_stops_being_an_owner(self):
        # Not the same as owning 0% — keeping them would put a 0.00% row on every screen forever.
        entries = [OwnershipEntry(1, d("90")), OwnershipEntry(2, d("10")), OwnershipEntry(2, d("-10"), counterparty_member_id=1)]
        assert replay_units(entries) == {1: d("100")}

    def test_replay_of_an_empty_ledger_owns_nothing(self):
        assert replay_units([]) == {}


class TestUnitPrice:
    def test_a_pot_with_no_units_has_no_price(self):
        # There is no honest price at which to issue units against nothing, so the flow must ask.
        assert unit_price(d("100"), d("0")) is None

    def test_a_pot_valued_at_zero_has_no_price(self):
        assert unit_price(d("0"), d("100")) is None

    def test_a_negative_nav_has_no_price(self):
        assert unit_price(d("-40"), d("100")) is None

    def test_the_price_is_rounded_to_six_places(self):
        # 100 / 3 = 33.3333333... -> 33.333333
        assert unit_price(d("100"), d("3")) == d("33.333333")


class TestRounding:
    def test_percentages_of_an_even_three_way_split_still_sum_to_one_hundred(self):
        # 10 / 30 = 33.3333...% each -> 33.33 x 3 = 99.99. The 0.01 remainder goes to one holder.
        pct = ownership_percentages({1: d("10"), 2: d("10"), 3: d("10")})
        assert pct == {1: d("33.34"), 2: d("33.33"), 3: d("33.33")}
        assert sum(pct.values()) == d("100.00")

    def test_the_remainder_goes_to_the_largest_holder(self):
        # 1/6, 1/6, 4/6 -> 16.67 + 16.67 + 66.67 = 100.01, so 0.01 comes OFF the largest holder.
        pct = ownership_percentages({1: d("1"), 2: d("1"), 3: d("4")})
        assert pct == {1: d("16.67"), 2: d("16.67"), 3: d("66.66")}
        assert sum(pct.values()) == d("100.00")

    def test_ties_for_largest_break_on_the_lowest_member_id(self):
        # Determinism matters: the same ledger must not produce different figures run to run.
        assert ownership_percentages({7: d("10"), 3: d("10"), 5: d("10")})[3] == d("33.34")

    def test_share_values_sum_to_exactly_the_nav(self):
        # 100 / 3 units against a NAV of 100: 33.33 x 3 = 99.99, remainder 0.01 to the largest.
        values = share_values({1: d("1"), 2: d("1"), 3: d("1")}, d("100"))
        assert values == {1: d("33.34"), 2: d("33.33"), 3: d("33.33")}
        assert sum(values.values()) == d("100.00")

    def test_share_values_do_not_compound_the_percentage_rounding(self):
        # Via percentages this would be 33.34% x 100000 = 33340.00, which is 6.67 adrift of the
        # honest figure. Deriving from units x price is what keeps it right.
        values = share_values({1: d("1"), 2: d("1"), 3: d("1")}, d("100000"))
        assert values == {1: d("33333.34"), 2: d("33333.33"), 3: d("33333.33")}

    def test_an_empty_pot_reports_no_percentages_rather_than_zeros(self):
        # "0%" asserts something the ledger has not said.
        assert ownership_percentages({}) == {}
        assert share_values({}, d("100")) == {}


class TestConversions:
    def test_units_for_amount_rounds_half_up_at_six_places(self):
        # 10 / 3 = 3.33333333... -> 3.333333
        assert units_for_amount(d("10"), d("3")) == d("3.333333")

    def test_amount_for_units_rounds_half_up_at_two_places(self):
        # 3.333333 x 3 = 9.999999 -> 10.00
        assert amount_for_units(d("3.333333"), d("3")) == d("10.00")

    def test_a_round_trip_through_both_is_stable_at_the_stored_precision(self):
        price = d("1.100000")
        assert amount_for_units(units_for_amount(d("5"), price), price) == d("5.00")

    def test_an_exact_half_rounds_up_rather_than_to_even(self):
        # Decimal's DEFAULT is banker's rounding, which would make this 1.00. These are figures a
        # person checks by hand, so the money convention (half-up) is the one that has to hold — and
        # nothing else in this file lands on a true .5 boundary, so without this the explicit
        # ROUND_HALF_UP is untested and could be deleted with every test still green.
        assert amount_for_units(d("1.005"), d("1")) == d("1.01")
        assert units_for_amount(d("0.0000005"), d("1")) == d("0.000001")

    def test_an_exact_half_in_a_percentage_also_rounds_up(self):
        # 1 / 160 = 0.625% exactly. Half-up gives 0.63; banker's rounding would give 0.62, and the
        # remainder rule would then hide the difference in the largest holder instead of surfacing it.
        assert ownership_percentages({1: d("1"), 2: d("159")}) == {1: d("0.63"), 2: d("99.37")}


class TestOpeningUnits:
    def test_a_single_owner_pot_is_legal(self):
        # How a buy-out ends, and how a private pot would be expressed.
        units = opening_units(d("500"), {1: d("100")})
        assert units == {1: d("500.000000")}
        assert ownership_percentages(units) == {1: d("100.00")}

    def test_fractional_percentages_are_honoured_not_rounded_to_whole_points(self):
        units = opening_units(d("1000"), {1: d("87.5"), 2: d("12.5")})
        assert units == {1: d("875.000000"), 2: d("125.000000")}

    def test_percentages_are_not_silently_normalised(self):
        # 90 + 5 does not make 100. Rescaling it here would turn what someone typed into a 94.7/5.3
        # split without telling them; the caller validates and rejects instead.
        units = opening_units(d("100"), {1: d("90"), 2: d("5")})
        assert units == {1: d("90.000000"), 2: d("5.000000")}
        assert total_units(units) == d("95.000000")


@pytest.mark.parametrize(
    ("nav", "balances", "expected_total"),
    [
        (d("115"), {1: d("90.000000"), 2: d("14.545455")}, d("115.00")),
        (d("0.01"), {1: d("1"), 2: d("1"), 3: d("1")}, d("0.01")),
        (d("999999.99"), {1: d("7"), 2: d("11"), 3: d("13")}, d("999999.99")),
    ],
)
def test_share_values_always_reconcile_to_the_nav(nav, balances, expected_total):
    assert sum(share_values(balances, nav).values()) == expected_total
