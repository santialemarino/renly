import type { Pot, PotHolding, PotHoldings, PotOwnershipEvent } from '@/lib/api/pots';

/*
 * What a pot's surface shows and offers, as pure functions over the API's own response.
 *
 * Extracted from the components for the reason `member-permissions.ts` was: these decide which
 * controls render at all, and every one of them mirrors a rule the API enforces. The API is the real
 * gate — a wrong answer here is a control that 403s or 409s rather than a hole — but "offered then
 * refused" is precisely the experience U6 says these flows must not have, so the predicates have to
 * agree with the backend exactly.
 *
 * Two distinctions carry most of the weight, and conflating either is the mistake to avoid:
 *
 *   * `hasLedger` (any event exists) is NOT `isDivided` (units are outstanding). A pot whose owners
 *     have all been bought out has a ledger and no units, and the API treats those states
 *     differently: a second opening is refused on the LEDGER (409 pot_already_opened) while a movement
 *     is refused on the UNITS (400 pot_not_opened).
 *   * seeing a pot and writing to it are separate questions, per V5/V6. Nothing here gates a read.
 */

// --- Identity ---

/*
 * A pot's label. A null name is the group's default pot, which A4 deliberately leaves unnamed: the
 * container is not a thing to manage until there is a second one to tell apart. The caller passes the
 * translated fallback, so the rule lives here and the words stay in the locale files.
 */
export function potLabel(pot: Pot, fallback: string): string {
  return pot.name?.trim() || fallback;
}

// --- What the ledger has said so far ---

/*
 * Whether the pot has any ownership history at all. This is what an opening and a holding move out are
 * gated on, because both are refused by the API the moment one event exists — regardless of whether
 * anyone still holds units.
 */
export function hasLedger(events: PotOwnershipEvent[]): boolean {
  return events.length > 0;
}

/*
 * Whether units are outstanding, which is what makes a unit price exist. `Number` is safe on a
 * NUMERIC(18,6) string for a `> 0` test: the smallest non-zero value is 1e-6, nowhere near float64's
 * underflow, so a positive can never read as zero.
 */
export function isDivided(pot: Pot): boolean {
  return Number(pot.totalUnits) > 0;
}

/*
 * Whether the pot can be priced today: a positive value AND units to divide it by. Both halves matter
 * — `unit_price` is undefined for either, and the API refuses rather than guessing
 * (400 pot_valuation_required), because a pot valued at zero has no honest price to issue units at.
 */
export function isPriceable(pot: Pot): boolean {
  return isDivided(pot) && pot.nav !== null && Number(pot.nav) > 0;
}

// --- Write predicates, one named rule each ---

// The opening is the division every later percentage derives from, so there is exactly one.
export function canRecordOpening(pot: Pot, events: PotOwnershipEvent[]): boolean {
  return pot.canWrite && !hasLedger(events);
}

// A contribution or withdrawal is priced at the pot's unit price on its date, so it needs one to exist.
export function canRecordMovement(pot: Pot): boolean {
  return pot.canWrite && isPriceable(pot);
}

/*
 * A re-agreement needs the same price a movement does, someone holding units to give, and a second
 * active seat to give them to. Separate from canRecordMovement rather than an alias: the seat count is
 * a condition a movement does not have, and one flag for both would offer this on a solo-seat pot.
 */
export function canRecordReagreement(pot: Pot, activeSeatCount: number): boolean {
  return canRecordMovement(pot) && pot.shares.length > 0 && activeSeatCount > 1;
}

// Moving holdings IN needs only write access — a pot can be filled before it is divided or after.
export function canMoveHoldingsIn(pot: Pot): boolean {
  return pot.canWrite;
}

/*
 * Moving a holding OUT is free only while nothing has been divided. Afterwards it would drop the pot's
 * value by the whole of that holding while nobody's units change, so every co-owner's share falls
 * pro-rata and it lands wholly in one person's private scope — one member taking joint assets, with no
 * cap on the amount. Taking value out of a divided pot is a withdrawal or a buy-out instead.
 */
export function canMoveHoldingsOut(pot: Pot, events: PotOwnershipEvent[]): boolean {
  return pot.canWrite && !hasLedger(events);
}

// Deleting a pot is group administration, not money movement, and the API refuses it while anything is
// still in there (409 pot_has_holdings) — archived holdings included, since they still point at it.
export function canDeletePot(isAdmin: boolean, holdings: PotHoldings): boolean {
  return isAdmin && holdings.investments.length === 0 && holdings.accounts.length === 0;
}

/*
 * Whether a movement recorded for this seat may name a private account at all.
 *
 * The API requires the private leg to be the CALLER's own account whoever the movement is recorded
 * for, so recording someone else's contribution can only ever be a note about money that moved
 * outside Renly. Offering the picker anyway would produce a 404 naming an account they can see.
 */
export function canNamePrivateLeg(memberId: number, myMemberId: number | null): boolean {
  return myMemberId !== null && memberId === myMemberId;
}

/*
 * The pot-side accounts a movement's leg may name: ones this pot actually holds, in its base currency
 * (which is what makes the credited figure unambiguous), and not archived — an archived account is
 * excluded from the pot's value, so money routed there would move the account and leave the NAV where
 * it was. The API refuses all three; this is what keeps them out of the picker.
 */
export function potLegAccounts(holdings: PotHoldings, baseCurrency: string): PotHolding[] {
  return holdings.accounts.filter((a) => a.isActive && a.currency === baseCurrency);
}

// --- Ledger rows ---

/*
 * The money figure one ledger row shows, and the currency it is in. There is deliberately no unit
 * count in it anywhere: U2 is that percentages go in and percentages come out, with units only in the
 * middle, so a raw unit count appears nowhere a person can see.
 *
 * Which figure that is depends on the event, and the three cases are genuinely different questions:
 *
 *   * an OPENING moved no money — its `baseAmount` is that owner's share of the value the baseline was
 *     measured at, which is the figure that makes the division legible;
 *   * a CONTRIBUTION or WITHDRAWAL moved real money, and `amount` is what actually left or arrived, in
 *     the private account's own currency. Showing the pot-side figure instead would report a number
 *     the person never transferred;
 *   * a RE-AGREEMENT moves no money at all, so the only honest figure is what the units transferred
 *     were worth on the day — `|units| x unitPrice`, in the pot's base currency.
 *
 * Returns null when there is nothing to state, and the row renders a dash rather than a zero.
 */
export function ownershipEventAmount(
  event: PotOwnershipEvent,
  baseCurrency: string,
): { amount: string; currency: string } | null {
  if (event.type === 'contribution' || event.type === 'withdrawal') {
    if (event.amount === null) return null;
    return { amount: event.amount, currency: event.amountCurrency ?? baseCurrency };
  }
  if (event.type === 'opening') {
    return event.baseAmount === null ? null : { amount: event.baseAmount, currency: baseCurrency };
  }
  return { amount: reagreementValue(event), currency: baseCurrency };
}

/*
 * What a re-agreement's transferred units were worth at the price it was recorded at — the one figure
 * in this module that is computed rather than read.
 *
 * The float product carries error (4.545455 x 1.1 is 5.000000499… in binary), and `toFixed(2)` is what
 * absorbs it. Rounding through integer cents FIRST, the way the installment total does, is redundant
 * here and was measured to be: over three million random unit/price pairs the two agree on every one.
 * The installment case is different because its product is SENT to the API, where a `decimal_places=2`
 * validator rejects 17.549999999999997 — there is no rounding step there to absorb it.
 *
 * `units` is signed against the member the event names and a re-agreement's is negative, so the
 * magnitude is what a money cell wants: the cell carries its own sign, and a negative figure inside one
 * would show the minus twice.
 *
 * DISPLAY only — never stored, never summed, never sent back — so the worst a pathological input costs
 * is a cent in a label, not a wrong balance.
 */
function reagreementValue(event: PotOwnershipEvent): string {
  return (Math.abs(Number(event.units)) * Number(event.unitPrice)).toFixed(2);
}

/*
 * Whether the row's money is leaving the pot, for the signed treatment. A withdrawal is the only event
 * that takes value out; a re-agreement moves it between people without changing the total, and an
 * opening and a contribution both add.
 */
export function isOutgoingEvent(event: PotOwnershipEvent): boolean {
  return event.type === 'withdrawal';
}
