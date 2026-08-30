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
def _payout_order(parts: dict[int, Decimal]) -> list[int]:
    return sorted(parts, key=lambda key: (-parts[key], key))


# Spreads a rounding remainder over already-rounded parts so they sum to `target` exactly, ONE minor
# unit at a time, starting from the largest part.
#
# One unit at a time rather than the whole remainder onto a single part, which is what the pot's own
# distribution does. The difference matters because these two figures are not the same kind of thing:
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
def spread_remainder(parts: dict[int, Decimal], target: Decimal, places: Decimal) -> dict[int, Decimal]:
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
