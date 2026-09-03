# The shared half of one person's net worth: their share of every pot they can see, plus what the
# groups they belong to owe them and what they owe back.
#
# THE governing rule, and the one every function here is shaped by (X1): your share of a co-owned asset
# genuinely is yours, so the dashboard's headline still answers "what am I worth" — and VISIBILITY NEVER
# INFLATES IT. A pot you may see but own none of contributes exactly zero while staying fully visible in
# the Shared module, and so does one whose owners have not agreed a division yet: before the baseline
# nobody owns any share of anything, and attributing it to whoever happened to move the holdings in
# would be the app inventing an ownership nobody recorded.
#
# An owed balance is its own net-worth line (D3): a receivable is an asset, a payable a liability,
# neither ever blended into cash. That is what makes settling up net-worth-neutral — cash arrives and
# the receivable clears — rather than looking like income.
#
# Balances NEVER net across currencies, exactly as the group hub's do not. Each bucket converts on its
# own and a bucket with no rate is dropped and REPORTED, never guessed at. Receivable and payable stay
# apart for the same reason the hub keeps them apart: owing dollars while being owed pesos is a real
# state, and one netted figure would hide which was which.
#
# Nothing here decides visibility. Which pots exist for this caller is RLS's answer plus the pot's own
# predicate (pot_service.list_visible_seats), and which groups they hold a seat in is the membership
# policy's — so a figure here can never disclose what a policy hides.

from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.money import MONEY_PLACES, assign_remainder, quantize
from app.models.group import GroupMember
from app.repositories import group_repository
from app.services import exchange_rate_service, group_settlement_service, pot_service
from app.utils.metrics import RateLookup, convert_value

ZERO = Decimal(0)


# A pot holding value that cannot be attributed to anybody yet, named so the dashboard can say why a
# holding that used to be in the headline no longer is. `name` is NULL for a group's default pot — A4
# leaves it unnamed deliberately — so the renderer supplies the fallback label rather than this layer
# inventing one, which is the arrangement the notification templates settled after shipping "None".
@dataclass(frozen=True)
class UndividedPot:
    pot_id: int
    name: str | None
    group_id: int


# The shared half of a net worth, in the display currency.
#
# `buckets` is the attribution the composition donut needs: this member's share of each pot, spread
# across the segments its holdings sit in, so a co-owned CEDEAR lands in `cedears` and a jointly-held
# bank account in `cash`. It sums to `pot_value` exactly.
#
# `has_shared` is EXISTENCE, not value — the distinction the dashboard's has_holdings already draws. A
# household whose balances net to zero this week still has a shared side worth showing; a solo user has
# none, and the surface renders nothing at all for them.
@dataclass(frozen=True)
class SharedWorth:
    pot_value: Decimal = ZERO
    receivable: Decimal = ZERO
    payable: Decimal = ZERO
    buckets: dict[str, Decimal] = field(default_factory=dict)
    undivided_pots: list[UndividedPot] = field(default_factory=list)
    has_shared: bool = False
    skipped_currencies: set[str] = field(default_factory=set)

    # What the shared side contributes to net worth: your share of what is held, plus what you are
    # owed, less what you owe. Legitimately negative — somebody who owes more than their pots are worth
    # is worth less for it, and the headline has to say so.
    @property
    def total(self) -> Decimal:
        return self.pot_value + self.receivable - self.payable


# Everything the shared side is read from, loaded once.
#
# The dashboard asks two questions of it in one request — what is it worth now, and what was it worth
# each month — and the reads behind both are the same three: which seats the caller holds, which pots
# they can see (with each pot's ledger), and how the groups' positions moved. Loading them once and
# passing the context down is what keeps a dashboard load from reading the same rows twice.
@dataclass(frozen=True)
class SharedContext:
    seats: list[GroupMember]
    pots: list[pot_service.PotSeat]
    # Cumulative positions at the end of every month that moved, ascending — see
    # group_settlement_service.get_positions_by_month.
    positions: list[tuple[tuple[int, int], dict[int, dict[str, dict[int, Decimal]]]]]

    @property
    def seat_ids(self) -> set[int]:
        return {seat.id for seat in self.seats}

    # Whether there is a shared side at all — EXISTENCE, not value, so a household whose balances
    # happen to net to zero this week still gets the breakdown and a solo user still gets nothing.
    @property
    def has_shared(self) -> bool:
        return bool(self.pots or self.seats)


async def load_context(session: AsyncSession, user_id: int) -> SharedContext:
    seats = await group_repository.list_active_members(session, user_id)
    pots = await pot_service.list_visible_seats(session, user_id)
    positions = await group_settlement_service.get_positions_by_month(session, sorted({seat.group_id for seat in seats}))
    return SharedContext(seats=seats, pots=pots, positions=positions)


# The first month the caller's shared side could be worth anything, or None when it never was.
#
# The dashboard's month grid starts at the earliest month ANY of its terms begins, and this is the
# shared term's answer. Two sources, and both are already in hand: a pot's ANCHOR — its earliest
# ownership event, or its creation when the ledger is empty, the same bound the pot page's own series
# uses — and the first month a group's flow rows moved a position.
def earliest_month(context: SharedContext) -> tuple[int, int] | None:
    candidates = [(anchor.year, anchor.month) for anchor in (_pot_anchor(seat) for seat in context.pots) if anchor is not None]
    if context.positions:
        candidates.append(context.positions[0][0])
    return min(candidates) if candidates else None


# The shared half of the caller's net worth at a date, converted to the display currency.
#
# One valuation per visible pot, which is the expensive part and is the same read the pot pages already
# pay for. §12's O3 is the standing note to re-measure it against real fan-out rather than assume it.
async def get_shared_worth(
    session: AsyncSession,
    user_id: int,
    context: SharedContext,
    *,
    currency: str | None,
    lookup: RateLookup | None,
    as_of_date: date_type,
) -> SharedWorth:
    if not context.has_shared:
        return SharedWorth()
    # A pot's holdings are converted into ITS OWN base currency before anything else, so a valuation
    # needs a lookup even when the caller asked for no display currency at all — but only a POT needs
    # one, and a group with balances and no pots is a real and common shape.
    pot_lookup = (lookup or await exchange_rate_service.get_user_rate_lookup(session, user_id)) if context.pots else None

    rate_map = lookup.get_rate_map_at(as_of_date) if lookup else None
    skipped: set[str] = set()
    pot_value = ZERO
    buckets: dict[str, Decimal] = {}
    undivided: list[UndividedPot] = []

    for seat in context.pots:
        share = await pot_service.get_member_share(session, seat, as_of_date=as_of_date, lookup=pot_lookup)
        if share.value is None:
            # A pot holding nothing is an empty container, not a half-finished setup: there is no
            # missing value to explain, so it stays silent instead of being listed.
            if share.holds_anything:
                undivided.append(UndividedPot(pot_id=seat.pot.id, name=seat.pot.name, group_id=seat.pot.group_id))
            continue
        converted = _to_display(share.value, seat.pot.base_currency, currency, rate_map)
        if converted is None:
            skipped.add(seat.pot.base_currency)
            continue
        pot_value += converted
        for bucket, value in _attribute(converted, share.weights, share.nav).items():
            buckets[bucket] = buckets.get(bucket, ZERO) + value

    receivable, payable, balance_skipped = _net_balances(context, currency=currency, rate_map=rate_map)
    return SharedWorth(
        pot_value=pot_value,
        receivable=receivable,
        payable=payable,
        buckets=buckets,
        undivided_pots=undivided,
        has_shared=True,
        skipped_currencies=skipped | balance_skipped,
    )


# The shared half at the END of each of the given months, one figure per month, ascending.
#
# The evolution chart needs this and the headline needs get_shared_worth, and the two must agree at the
# last point — so both fold the SAME two sources through the same rules: pot_service's share series
# (which is also the pot page's) and group_settlement_service's position algebra.
#
# Each month converts at its own month-end rate, which is what the private side does term by term, so
# every part of a month's net worth is priced in one frame.
#
# A pot whose share is unknown at a point contributes ZERO there rather than making the whole point
# unknown, and that deliberately differs from the NAV's own refusal rule. A NAV missing a term is not a
# smaller NAV; a net-worth chart missing one person's share of one pot is still the honest answer for
# everything else they hold, and blanking the line would hide a whole private portfolio because a
# co-owner forgot a snapshot. A currency that could not be converted is reported either way.
async def get_shared_series(
    session: AsyncSession,
    user_id: int,
    context: SharedContext,
    *,
    months: list[tuple[int, int]],
    month_ends: list[date_type],
    currency: str | None,
    lookup: RateLookup | None,
) -> tuple[list[Decimal], set[str]]:
    values = [ZERO for _ in month_ends]
    if not month_ends or not context.has_shared:
        return (values, set())

    pot_lookup = (lookup or await exchange_rate_service.get_user_rate_lookup(session, user_id)) if context.pots else None
    skipped: set[str] = set()

    for seat in context.pots:
        points = await pot_service.compute_share_series(
            session,
            seat.pot,
            seat.member_id,
            dates=month_ends,
            events=seat.events,
            lookup=pot_lookup,
        )
        for index, point in enumerate(points):
            if point.my_value is None:
                continue
            rate_map = lookup.get_rate_map_at(month_ends[index]) if lookup else None
            converted = _to_display(point.my_value, seat.pot.base_currency, currency, rate_map)
            if converted is None:
                skipped.add(seat.pot.base_currency)
                continue
            values[index] += converted

    # Forward-filled over the positions series, which carries only the months that moved: a month with
    # no rows stands where the previous one left it, and months before the first are simply square.
    cursor = 0
    standing: dict[int, dict[str, dict[int, Decimal]]] = {}
    for index, month_key in enumerate(months):
        while cursor < len(context.positions) and context.positions[cursor][0] <= month_key:
            standing = context.positions[cursor][1]
            cursor += 1
        rate_map = lookup.get_rate_map_at(month_ends[index]) if lookup else None
        for (_group_id, bucket_currency), mine in _my_buckets(standing, context.seat_ids).items():
            converted = _to_display(mine, bucket_currency, currency, rate_map)
            if converted is None:
                skipped.add(bucket_currency)
                continue
            values[index] += converted
    return (values, skipped)


# --- Internal ---


# The earliest date a pot could be worth anything to anybody: its first ownership event, or its
# creation when the ledger is empty. The same bound the pot page's own series uses — a shared
# investment brings its whole snapshot history with it, so without it a pot created yesterday would
# report years of value for a pot that did not exist.
def _pot_anchor(seat: pot_service.PotSeat) -> date_type | None:
    created = seat.pot.created_at.date() if seat.pot.created_at is not None else None
    if not seat.events:
        return created
    first = seat.events[0].date
    return first if created is None else min(first, created)


# One figure restated in the display currency, or None when it cannot be. Returns the value unchanged
# when nothing was asked to be converted — the "Original" posture every other dashboard total takes,
# where figures sum raw rather than being dropped.
def _to_display(value: Decimal, from_currency: str, target_currency: str | None, rate_map: dict[str, Decimal] | None) -> Decimal | None:
    if not target_currency or from_currency == target_currency:
        return value
    if rate_map is None:
        return None
    return convert_value(value, from_currency, target_currency, rate_map)


# Spreads one member's already-converted share of a pot across the composition segments its holdings
# sit in, pro rata to what each contributed to the NAV.
#
# Attributed AFTER the conversion on purpose: converting each bucket separately and summing them leaves
# the parts a cent or two off the whole, and the whole is the figure the headline shows. This way they
# sum to it exactly, with assign_remainder putting the odd cent on the largest segment — the rule every
# other derived-for-display division in the app already uses.
def _attribute(converted_share: Decimal, weights: dict[str, Decimal], nav: Decimal | None) -> dict[str, Decimal]:
    if not weights or nav is None or nav <= ZERO:
        return {}
    parts = {bucket: quantize(converted_share * weight / nav, MONEY_PLACES) for bucket, weight in weights.items()}
    return assign_remainder(parts, converted_share, MONEY_PLACES)


# This member's own position in every bucket they hold one in, keyed by (group_id, currency).
#
# Kept at that granularity rather than summed per currency, and the reason is D3: a claim on one group
# is an ASSET and a debt to another is a LIABILITY, so netting them before the split would report one
# figure and lose which was which. It is also the atom a settle-up already works in — one group, one
# currency — so the dashboard's figures decompose into the buckets the group hub shows.
#
# Both callers convert at this granularity for a second reason: the headline and the chart must agree,
# and they only do if they round the same figures the same number of times.
def _my_buckets(by_group: dict[int, dict[str, dict[int, Decimal]]], seat_ids: set[int]) -> dict[tuple[int, str], Decimal]:
    mine: dict[tuple[int, str], Decimal] = {}
    for group_id, by_currency in by_group.items():
        for bucket_currency, net in by_currency.items():
            amount = sum((value for member_id, value in net.items() if member_id in seat_ids), ZERO)
            if amount != ZERO:
                mine[(group_id, bucket_currency)] = amount
    return mine


# What the caller's groups owe them and what they owe back, as two totals in the display currency.
#
# Converted per bucket and split by SIGN before summing: a positive bucket is an asset and a negative
# one is a liability, so netting them first would put both through one figure and lose which was which
# — exactly what D3 says a net-worth line must not do.
#
# It reads the LAST entry of the context's monthly series rather than issuing the live balance query,
# and the two are the same figure by construction: positions are a running sum over every row, so the
# most recent month that moved IS today's position (asserted against the live read in
# tests/integration/test_shared_flow_queries.py). Asking twice would cost three more queries per
# dashboard load and, worse, put two derivations behind two figures a reader compares side by side.
def _net_balances(
    context: SharedContext,
    *,
    currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> tuple[Decimal, Decimal, set[str]]:
    if not context.positions:
        return (ZERO, ZERO, set())
    by_group = context.positions[-1][1]
    receivable = ZERO
    payable = ZERO
    skipped: set[str] = set()
    for (_group_id, bucket_currency), mine in _my_buckets(by_group, context.seat_ids).items():
        converted = _to_display(mine, bucket_currency, currency, rate_map)
        if converted is None:
            skipped.add(bucket_currency)
            continue
        if converted > ZERO:
            receivable += converted
        else:
            payable += -converted
    return (receivable, payable, skipped)
