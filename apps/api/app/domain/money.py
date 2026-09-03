# Money and percentage rounding shared by every flow that divides one figure between several people.
#
# Extracted from the pot's unit math when shared expenses needed the same two operations. They are
# here rather than in `app/utils/` because they are domain rules, not general arithmetic: which
# rounding mode, how many places, and who absorbs the remainder are all answers this product gives.

from decimal import ROUND_HALF_UP, Decimal

# NUMERIC(18,2), the width every money column in the schema uses. Renly is uniformly two-decimal:
# there is no per-currency precision layer, so a 0-decimal currency is stored and rounded at two like
# every other. Introducing one is a schema-wide change, not a per-feature one.
MONEY_PLACES = Decimal("0.01")
PERCENT_PLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")


# Rounds a value half-up to the given places. Half-up rather than Decimal's banker's-rounding default
# because these are money and percentage figures a person reads and checks by hand.
def quantize(value: Decimal, places: Decimal) -> Decimal:
    return value.quantize(places, rounding=ROUND_HALF_UP)


# Returns the parts in the order the remainder is handed out: largest first, ties broken by the lowest
# key, so the same input always produces the same output rather than depending on dict ordering.
# Generic over the key because both rules below divide two different kinds of thing — member ids in the
# flow layer, composition labels on the dashboard — and a key type only has to be orderable against its
# own kind.
def _payout_order[K](parts: dict[K, Decimal]) -> list[K]:
    return sorted(parts, key=lambda key: (-parts[key], key))


# The remainder rule for figures that are DERIVED FOR DISPLAY and recomputed on every read: the whole
# remainder goes to the largest part, so the parts sum to `target` exactly.
#
# The sibling of spread_remainder, and the two are deliberately different rules for different kinds of
# figure. Stored money somebody owes accumulates across every row a group ever records, so that one
# hands out one minor unit at a time and bounds each member's share of the rounding to exactly one.
# Nothing here accumulates — a pot's percentages, a member's share of a NAV, a composition slice are
# all recomputed from scratch — so the simpler rule is enough, and it keeps the largest holder's figure
# the one that absorbs a cent rather than scattering cents over parts a reader would then check.
#
# Returns the parts unchanged when there is nothing to distribute or nowhere to put it.
def assign_remainder[K](parts: dict[K, Decimal], target: Decimal, places: Decimal) -> dict[K, Decimal]:
    if not parts:
        return parts
    remainder = quantize(target - sum(parts.values()), places)
    if remainder == 0:
        return parts
    largest = _payout_order(parts)[0]
    return {key: (value + remainder if key == largest else value) for key, value in parts.items()}


# Spreads a rounding remainder over already-rounded parts so they sum to `target` exactly, ONE minor
# unit at a time, starting from the largest part.
#
# One unit at a time rather than the whole remainder onto a single part, which is what assign_remainder
# above does. The difference matters because these two figures are not the same kind of thing:
# a pot's percentages are derived for display and recomputed on every read, whereas a split amount is
# stored money somebody owes and accumulates across every expense a group ever records. Handing the
# entire remainder to one member would put up to (n-1) minor units on them, every time; this bounds
# each member's share of it to exactly one.
#
# D30 suggests giving the leftover to the payer. That is not taken here because the payer is not
# always a single member (a shared account is fronted by the pot's owners in their proportions) and is
# not always a participant at all (D33), so it has no part to add to. This rule is total.
#
# Returns the parts unchanged when there is nothing to distribute, or when there is nowhere to put it.
def spread_remainder[K](parts: dict[K, Decimal], target: Decimal, places: Decimal) -> dict[K, Decimal]:
    if not parts:
        return parts
    remainder = quantize(target - sum(parts.values()), places)
    if remainder == 0:
        return parts
    step = places if remainder > 0 else -places
    adjusted = dict(parts)
    order = _payout_order(parts)
    # `units` is how many minor units are outstanding; each pass hands one to the next part in order,
    # wrapping if the remainder is larger than the number of parts (which a same-currency split cannot
    # produce, but a caller dividing by a rate could).
    units = int(abs(remainder) / places)
    for index in range(units):
        key = order[index % len(order)]
        adjusted[key] = adjusted[key] + step
    return adjusted
