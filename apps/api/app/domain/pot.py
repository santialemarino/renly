# Unit accounting: the math that divides one pot between several owners.
#
# The model in one paragraph. Each owner holds UNITS of the pot. The unit price is the pot's value
# (NAV) divided by the units outstanding, so growth is pro-rata with no event at all — nobody has to
# record anything when the market moves. Money in or out issues or redeems units AT THAT DATE'S
# PRICE, which dilutes percentages without ever moving value between people. That is the whole reason
# for units: percentages alone cannot express "he added 5 and nobody else lost anything".
#
# Everything here is pure. Unit balances are DERIVED by replaying the ledger in order and nothing is
# stored as a running total, exactly as every other balance in Renly works — which is also what makes
# back-dating an ownership event safe: inserting an earlier one simply recomputes the series, rather
# than rewriting recorded history the way a reconciliation adjustment would.
#
# Percentages and share values are both rounded to 2 places and both carry their rounding remainder
# to the largest holder, so the displayed parts sum to exactly 100% and to exactly the NAV. Without
# that a user reads three numbers that visibly fail to add up and correctly stops trusting all three.

from dataclasses import dataclass
from decimal import Decimal

from app.domain.money import MONEY_PLACES, ONE_HUNDRED, PERCENT_PLACES, assign_remainder, quantize

# NUMERIC(18,6) on pot_ownership_events.units and .unit_price — the precedent snapshots and
# transactions already set for quantity.
UNIT_PLACES = Decimal("0.000001")
# The nominal price the opening baseline issues units at, so opening units read as the percentages
# they were entered as (90% of 100 is 90 units) instead of an arbitrary scaled count.
OPENING_UNIT_PRICE = Decimal("1")


# One replayable entry from a pot's ownership ledger, decoupled from the ORM row so the math can be
# tested without a database and reused by the service without loading models it does not need.
# `units` is ALWAYS the signed change to `member_id`'s balance — positive issues, negative redeems —
# and never varies its meaning by event type. A reagreement additionally names a counterparty, who
# receives exactly the negation, which is what makes it net-zero in units by construction rather than
# by the caller remembering to balance it.
@dataclass(frozen=True)
class OwnershipEntry:
    member_id: int
    units: Decimal
    counterparty_member_id: int | None = None


# Replays a pot's ledger into each member's unit balance. Entries must already be ordered by date
# then id — the caller owns that, because "the order events happened in" is a query concern.
# A member whose balance nets to exactly zero is dropped: they held units and no longer do, which is
# not the same as being an owner of 0%, and keeping them would put a 0.00% row on every screen for
# everyone who has ever been bought out.
def replay_units(entries: list[OwnershipEntry]) -> dict[int, Decimal]:
    balances: dict[int, Decimal] = {}
    for entry in entries:
        balances[entry.member_id] = balances.get(entry.member_id, Decimal(0)) + entry.units
        if entry.counterparty_member_id is not None:
            balances[entry.counterparty_member_id] = balances.get(entry.counterparty_member_id, Decimal(0)) - entry.units
    return {member_id: units for member_id, units in balances.items() if units != 0}


# Total units outstanding — the denominator of the unit price.
def total_units(balances: dict[int, Decimal]) -> Decimal:
    return sum(balances.values(), Decimal(0))


# The price of one unit at a date: NAV divided by units outstanding.
# Returns None when the price is undefined rather than guessing, which happens in two ways that look
# different to a user but are the same division: no units issued yet (the pot has no baseline), or a
# NAV of zero or less. A pot cannot be valued at <= 0 for ownership purposes — there is no honest
# price at which to issue units against nothing — so the flow asks for a valuation instead.
def unit_price(nav: Decimal, units_outstanding: Decimal) -> Decimal | None:
    if units_outstanding <= 0 or nav <= 0:
        return None
    return quantize(nav / units_outstanding, UNIT_PLACES)


# How many units a sum of money buys at a given price. Used by contributions (issuing) and
# withdrawals (redeeming) alike — a withdrawal negates the result rather than using different math.
def units_for_amount(amount: Decimal, price: Decimal) -> Decimal:
    return quantize(amount / price, UNIT_PLACES)


# What a number of units is worth at a given price. The inverse of units_for_amount, to 2 places.
def amount_for_units(units: Decimal, price: Decimal) -> Decimal:
    return quantize(units * price, MONEY_PLACES)


# Each member's ownership percentage, summing to exactly 100 (see assign_remainder).
# An empty pot returns no rows rather than a set of zeros: with no units outstanding nobody owns any
# share of anything, and "0%" would assert something the ledger has not said.
def ownership_percentages(balances: dict[int, Decimal]) -> dict[int, Decimal]:
    outstanding = total_units(balances)
    if outstanding <= 0:
        return {}
    parts = {member_id: quantize(units / outstanding * ONE_HUNDRED, PERCENT_PLACES) for member_id, units in balances.items()}
    return assign_remainder(parts, ONE_HUNDRED, PERCENT_PLACES)


# Each member's share of the pot in its base currency, summing to exactly the NAV.
# Deliberately derived from units x price rather than from percentage x NAV: the percentages are
# already rounded, so going through them would compound one rounding into the money figure.
def share_values(balances: dict[int, Decimal], nav: Decimal) -> dict[int, Decimal]:
    outstanding = total_units(balances)
    if outstanding <= 0:
        return {}
    price = nav / outstanding
    parts = {member_id: quantize(units * price, MONEY_PLACES) for member_id, units in balances.items()}
    return assign_remainder(parts, quantize(nav, MONEY_PLACES), MONEY_PLACES)


# Turns an opening baseline — a total value and each owner's percentage — into the units to issue.
# This IS the division baseline (the pot's equivalent of accounts.opening_balance / opening_date):
# nothing before its date is in scope. Units are issued at a nominal 1.00, so the opening unit count
# reads back as the percentage it was entered as.
# The caller validates that the percentages sum to 100; this function does not silently normalise
# them, because quietly rescaling what someone typed is how a 90/5 split becomes a 94.7/5.3 one.
def opening_units(value: Decimal, percentages: dict[int, Decimal]) -> dict[int, Decimal]:
    return {member_id: quantize(value * pct / ONE_HUNDRED / OPENING_UNIT_PRICE, UNIT_PLACES) for member_id, pct in percentages.items()}


# Refuses a private entry funded from a co-owned account. The money really leaves the shared account,
# so the pot's value drops and every co-owner's share falls with it — one person spending, everyone
# paying, with nothing recording it. Crossing a scope boundary is an ownership event, never a flow,
# which is the same rule that keeps a transfer inside one scope.
# Takes the account row rather than an id so the caller has already proven it is reachable, and does
# nothing at all when no account is named or the account is private — the case for every solo user.
def ensure_private_funding(account) -> None:
    from app.domain.errors import PrivateEntryFromSharedAccountError

    if account is not None and getattr(account, "pot_id", None) is not None:
        raise PrivateEntryFromSharedAccountError()


# Refuses a transfer whose two legs sit in different scopes. A transfer is net-worth-neutral BY
# CONSTRUCTION, and that is only true within one scope: moving joint money into a personal account
# takes value from the other owners, which is emphatically not neutral. Such a movement is a
# contribution or a withdrawal, recorded on the pot's ownership ledger where it is priced and where
# the units it issues or redeems say whose money it now is.
# Compares pot_id on both sides, so private-to-private (both NULL) and same-pot both pass.
def ensure_same_scope(source, destination) -> None:
    from app.domain.errors import TransferCrossScopeError

    if getattr(source, "pot_id", None) != getattr(destination, "pot_id", None):
        raise TransferCrossScopeError()
