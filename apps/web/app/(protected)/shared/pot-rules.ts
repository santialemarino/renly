import type {
  Pot,
  PotHolding,
  PotHoldings,
  PotMemberShare,
  PotOwnershipEvent,
  PotValueSeries,
} from '@/lib/api/pots';

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

// --- The guided flows ---

/*
 * Which panel "share something you own" opens on. DERIVED from what the server already has, never
 * remembered, and that is the whole design: the flow makes three writes that no transaction spans
 * (create the pot, move the holdings in, record the baseline), so a failure or a closed tab after any
 * of them has to be recoverable. Re-entering reads the same three facts and lands on the first thing
 * still missing, so there is no half-made pot the app cannot talk about — and no wizard state to
 * persist or invalidate.
 *
 * The order the writes happen in is what makes that safe, and it is not interchangeable: holdings can
 * still leave a pot while its ownership has NOT been agreed (409 pot_already_divided afterwards), so
 * the baseline goes last and everything before it is still undoable by hand.
 *
 * `divided` is not a step. A pot with any ownership history cannot take a baseline at all
 * (409 pot_already_opened), so the flow says so and points at the pot instead of offering a form that
 * would be refused.
 */
export type SharePotStage = 'pick' | 'value' | 'shares' | 'confirm' | 'done' | 'divided';

export interface SharePotProgress {
  holdings: PotHoldings;
  events: PotOwnershipEvent[];
}

/*
 * `null` is "there is no pot yet", which is the only way the three facts can be partly absent: the
 * page fetches them together, so it either has all of them or none. Taking one nullable argument
 * rather than three says that, and it removed two clauses that no caller could ever falsify — a
 * mutation sweep proved both survived being deleted.
 */
export function shareWizardEntry(progress: SharePotProgress | null): SharePotStage {
  if (progress === null) return 'pick';
  if (hasLedger(progress.events)) return 'divided';
  const holdsNothing =
    progress.holdings.investments.length === 0 && progress.holdings.accounts.length === 0;
  return holdsNothing ? 'pick' : 'value';
}

/*
 * Whether a share can be taken out of the pot. A movement's own conditions, plus somebody actually
 * holding a share to take — which the flow needs and a plain movement does not, because it opens on
 * "whose share" rather than on an amount.
 */
export function canTakeShareOut(pot: Pot): boolean {
  return canRecordMovement(pot) && pot.shares.length > 0;
}

// One member's share row, or undefined when they hold none. Every guided flow branches on this, and
// "holds nothing" is a real state: a bought-out member keeps their seat and loses their row.
export function holderShare(pot: Pot, memberId: number): PotMemberShare | undefined {
  return pot.shares.find((share) => share.memberId === memberId);
}

/*
 * What the pot looks like after one member's whole share leaves, in the only terms the flow can state
 * honestly WITHOUT reproducing the backend's rounding.
 *
 * The resulting percentages are computed server-side and carry their rounding remainder to the largest
 * holder, so predicting them here would be a second copy of an algorithm that has to agree exactly —
 * and the one figure a second copy gets wrong is the one a person checks. These three cases need no
 * arithmetic at all: nobody is left, exactly one person is left (so they own all of it, which is 100%
 * by definition rather than by calculation), or several are (so they keep the same proportions to each
 * other, which is what pro-rata means). The real figures come from the refreshed pot afterwards.
 */
export type WholeExitOutcome = 'nobodyLeft' | 'oneHolderLeft' | 'severalHoldersLeft';

export function wholeExitOutcome(pot: Pot, memberId: number): WholeExitOutcome {
  const remaining = pot.shares.filter((share) => share.memberId !== memberId);
  if (remaining.length === 0) return 'nobodyLeft';
  return remaining.length === 1 ? 'oneHolderLeft' : 'severalHoldersLeft';
}

/*
 * Whether buying this seller out leaves the buyer holding the whole pot.
 *
 * Deliberately NOT wholeExitOutcome. That one answers "who is left after a share leaves", which is the
 * question a withdrawal asks; a buy-out's units do not leave — the buyer receives them — so its answer
 * turns on whether anyone OTHER than those two holds a share. Reusing the withdrawal's three cases here
 * produced a sentence about nobody being left, on a flow where somebody always is.
 */
export function buyOutLeavesOneHolder(pot: Pot, sellerId: number, buyerId: number): boolean {
  return pot.shares.every((share) => share.memberId === sellerId || share.memberId === buyerId);
}

/*
 * The base currency to offer for a pot about to hold these things: the one most of them are already
 * denominated in.
 *
 * Not a convenience. Every ownership figure is measured in the pot's base currency, and a movement's
 * pot-side leg must be an account in it (potLegAccounts, and the API refuses otherwise) — so a pot
 * created in a currency none of its accounts use has no usable cash leg at all, and the first
 * contribution someone tries is refused for a reason nothing on screen explains.
 *
 * Ties break on first appearance rather than alphabetically, so the answer follows the order the user
 * sees their own holdings in rather than an ordering they have no view of.
 */
export function suggestedBaseCurrency(currencies: string[]): string | null {
  const counts = new Map<string, number>();
  currencies.forEach((currency) => counts.set(currency, (counts.get(currency) ?? 0) + 1));
  // A Map iterates in insertion order, so `>` alone leaves the first-seen currency holding a tie.
  const winner = [...counts.entries()].reduce<[string, number] | null>(
    (best, entry) => (best === null || entry[1] > best[1] ? entry : best),
    null,
  );
  return winner === null ? null : winner[0];
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

// --- Monitoring ---

/*
 * What the header's value tile says, as a state rather than a nested ternary.
 *
 * The as-of date is appended only when there IS a figure. When the value cannot be stated at all,
 * "not valued" is the whole answer — a date beside it would describe the freshness of numbers the
 * tile is not showing, which is the case a pot whose holdings are all snapshotted but one of which
 * cannot be converted actually reaches (a real `valuedAsOf`, a null `nav`).
 *
 * Returns the figures rather than only a tag, so the caller formats what the rule selected instead of
 * re-checking the same two nulls to satisfy the type — a second copy of the rule, and one free to
 * drift from it.
 */
export type PotValueDisplay =
  | { kind: 'unvalued' }
  | { kind: 'value'; nav: string }
  | { kind: 'valueAsOf'; nav: string; valuedAsOf: string };

export function potValueDisplay(pot: Pot): PotValueDisplay {
  if (pot.nav === null) return { kind: 'unvalued' };
  if (pot.valuedAsOf === null) return { kind: 'value', nav: pot.nav };
  return { kind: 'valueAsOf', nav: pot.nav, valuedAsOf: pot.valuedAsOf };
}

/*
 * Which freshness sentence the header shows, if any.
 *
 * Two states rather than one, because "nobody has ever valued this" and "the last valuation is older
 * than the cadence allows" are different problems: the first means the pot cannot be priced at all,
 * so no contribution or withdrawal can be recorded against it, while the second still leaves a
 * usable — if dated — figure. Calling the first one "overdue" would understate it.
 *
 * Carries the date for the same reason potValueDisplay carries the figure.
 */
export type PotFreshnessNotice =
  | { kind: 'none' }
  | { kind: 'neverValued' }
  | { kind: 'overdue'; valuedAsOf: string };

export function potFreshnessNotice(pot: Pot): PotFreshnessNotice {
  if (!pot.isStale) return { kind: 'none' };
  return pot.valuedAsOf === null
    ? { kind: 'neverValued' }
    : { kind: 'overdue', valuedAsOf: pot.valuedAsOf };
}

// How many points of the series carry a figure. Both the caption's subject and the gate on rendering a
// chart at all: a window in which nothing could be valued has no line to draw, only a sentence.
export function valuedPointCount(series: PotValueSeries): number {
  return series.points.filter((point) => point.nav !== null).length;
}

/*
 * Whether the section can state its coverage as "valued in x of the last y".
 *
 * Two ways it cannot. With nothing valued there is no chart to describe, and with a single period it
 * is not a sentence — "valued in 1 of the last 1 months" is exactly what a pot created today
 * produces, which is the FIRST thing anyone sees after the sharing flow rather than an edge case.
 * Both fall back to the plain description, which is true whatever the window holds.
 */
export const MIN_COVERAGE_PERIODS = 2;

export function showsCoverage(series: PotValueSeries): boolean {
  return valuedPointCount(series) > 0 && series.points.length >= MIN_COVERAGE_PERIODS;
}

/*
 * Whether the viewer's own share is worth drawing as a second series.
 *
 * False for a member who holds none of the pot anywhere in the window — which is a real state (V3: a
 * member owning 0% still sees everything), and a legend entry for a line that is never drawn is a
 * promise the chart does not keep.
 */
export function seriesHasShare(series: PotValueSeries): boolean {
  return series.points.some((point) => point.myValue !== null);
}
