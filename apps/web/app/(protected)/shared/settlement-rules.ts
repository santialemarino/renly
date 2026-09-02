import type { Account } from '@/lib/api/accounts';
import type {
  GroupCurrencyBalance,
  GroupSettlement,
  GroupSettlementPlan,
  GroupSettlementPlanBucket,
  GroupSettleSuggestion,
} from '@/lib/api/group-settlements';

/*
 * What the balances and settle-up surface shows and offers, as pure functions over the API's own
 * response. Same shape and same reasoning as `pot-rules.ts`.
 *
 * Three of the API's rules are load-bearing here and none of them is re-derived:
 *
 *   * `canConfirm` and `canDelete` are resolved SERVER-SIDE and are read as given. Nothing below
 *     recomputes either — a second copy of a permission check is a second thing that can disagree
 *     with the gate that actually decides.
 *   * The two rules the response does NOT carry — who may take a confirmation back, and whose cash
 *     leg a caller may attach — are mirrored here, deliberately and in one place, because the
 *     alternative is a control that 403s. Both are stated in the same two facts the response does
 *     carry: the status, and which seat the caller holds.
 *   * A settlement's two legs belong to two different people. Nothing here ever offers the other
 *     party's side, because the row-level policies hide their accounts and the API refuses it
 *     outright (400 group_settlement_foreign_leg).
 */

// --- The caller's side of a settlement ---

/*
 * Which leg is the caller's, or null when they are on neither side.
 *
 * The one question every leg control asks first, and the reason it is a case rather than two
 * booleans: the payer's leg and the payee's are the same field on the form with opposite meanings —
 * what left, and what arrived — so a caller that got the side wrong would write the wrong column.
 */
export type SettlementSide = 'outgoing' | 'incoming';

export function ownSettlementSide(
  settlement: GroupSettlement,
  mySeatId: number | null,
): SettlementSide | null {
  // No explicit null-seat guard: a seat id is a number, so a null viewer matches neither side and
  // falls out of the comparisons below anyway. A guard here would be a branch nothing can reach —
  // a mutation sweep proved it could be deleted with every test still green.
  if (settlement.fromMemberId === mySeatId) return 'outgoing';
  return settlement.toMemberId === mySeatId ? 'incoming' : null;
}

/*
 * Whether the caller may attach or clear their own cash leg.
 *
 * Allowed in any status EXCEPT a write-off, which moved no money to attach an account to (the API
 * answers 409 group_settlement_write_off_has_no_leg). A confirmed settlement is deliberately not
 * locked against this the way it is against deletion: what confirmation vouches for is the amount and
 * the fact of the payment, and neither changes here — only which of the caller's own accounts it
 * passed through, which is theirs to state and moves nobody else's balance.
 */
export function canAttachOwnLeg(settlement: GroupSettlement, mySeatId: number | null): boolean {
  return settlement.status !== 'written_off' && ownSettlementSide(settlement, mySeatId) !== null;
}

/*
 * Whether the caller may take a confirmation back.
 *
 * The payee's alone, for the same reason only they may give it: it is their word being withdrawn.
 * Mirrored here rather than read off the response because the response has no field for it — and it
 * is the ONLY way out of a confirmed settlement, which cannot be deleted by anybody until it is
 * pending again. Left underivable, a confirmed settlement recorded by mistake would have no exit.
 */
export function canUnconfirmSettlement(
  settlement: GroupSettlement,
  mySeatId: number | null,
): boolean {
  return (
    settlement.status === 'confirmed' && ownSettlementSide(settlement, mySeatId) === 'incoming'
  );
}

// The account already attached on the caller's own side, and what moved through it. Null on the side
// they are not on, so a form opening on someone else's settlement starts empty rather than prefilled
// with a leg it may not write.
export function ownLegAccountId(
  settlement: GroupSettlement,
  mySeatId: number | null,
): number | null {
  const side = ownSettlementSide(settlement, mySeatId);
  if (side === null) return null;
  return side === 'outgoing' ? settlement.fromAccountId : settlement.toAccountId;
}

export function ownLegAmount(settlement: GroupSettlement, mySeatId: number | null): string | null {
  const side = ownSettlementSide(settlement, mySeatId);
  if (side === null) return null;
  return side === 'outgoing' ? settlement.fromAmount : settlement.toAmount;
}

// --- Suggestions ---

/*
 * Whether the caller is the one being paid in this suggested payment, which is what makes a write-off
 * theirs to record: giving up a claim is the creditor's to give up (403 group_settlement_not_creditor
 * otherwise), and the other way round would be one person deciding on somebody else's behalf.
 */
export function canWriteOffSuggestion(
  suggestion: GroupSettleSuggestion,
  mySeatId: number | null,
): boolean {
  return mySeatId !== null && suggestion.toMemberId === mySeatId;
}

/*
 * Which sentence a suggested payment is stated in — the caller paying, the caller being paid, or two
 * other people settling between themselves.
 *
 * A named function rather than a ternary at the call site because it is ORDER-DEPENDENT with no
 * other guard: swap the first two branches and a plausible-but-wrong line appears ("Nico pays you"
 * where you owe Nico), which no type check can see and which a reader would believe.
 */
export type SuggestionVoice = 'youPay' | 'paysYou' | 'pays';

export function suggestionVoice(
  suggestion: GroupSettleSuggestion,
  mySeatId: number | null,
): SuggestionVoice {
  if (mySeatId !== null && suggestion.fromMemberId === mySeatId) return 'youPay';
  if (mySeatId !== null && suggestion.toMemberId === mySeatId) return 'paysYou';
  return 'pays';
}

/*
 * Which leg the caller would record if they settled this suggestion, or null when they are neither
 * party — which is a real case, since any member may write down a payment between two others.
 *
 * Defined in terms of the voice above rather than repeating its two comparisons, so the sentence the
 * dialog says and the column it writes to cannot come apart: "you pay" and "the money left my
 * account" are the same fact stated twice, and the failure worth designing out is them disagreeing.
 */
export function suggestionSide(
  suggestion: GroupSettleSuggestion,
  mySeatId: number | null,
): SettlementSide | null {
  const voice = suggestionVoice(suggestion, mySeatId);
  if (voice === 'youPay') return 'outgoing';
  return voice === 'paysYou' ? 'incoming' : null;
}

// --- Standing ---

/*
 * The caller's standing in one bucket, as a state rather than a sign test repeated per surface.
 *
 * `square` is its own answer rather than a zero, because the sentence is different in kind: being
 * owed nothing and owing nothing is a resolved state, not a small amount. `Number` is safe on a
 * NUMERIC(18,2) string for a sign test — no rounding can move a value across zero.
 */
export type BalanceStanding = 'owed' | 'owing' | 'square';

export function balanceStanding(amount: string): BalanceStanding {
  const value = Number(amount);
  if (value > 0) return 'owed';
  return value < 0 ? 'owing' : 'square';
}

/*
 * The magnitude of a signed balance, as a string, for a cell that carries its own sign.
 *
 * A minus inside a cell that already prefixes one shows it twice — the same reason `pot-rules`
 * takes the magnitude of a re-agreement's signed units. `.replace` rather than arithmetic so the
 * decimal string reaches the formatter with the precision the API sent, never through a JS number.
 */
export function balanceMagnitude(amount: string): string {
  return amount.startsWith('-') ? amount.slice(1) : amount;
}

// --- The settle form ---

/*
 * Whether a cash leg crosses currencies — exactly when the API requires the leg's own amount to be
 * stated (400 group_settlement_leg_amount_required) and exactly when it stores one.
 *
 * Within one currency the account moved what the bucket cleared, and the API refuses a different
 * figure rather than quietly preferring it, so the field there is not merely unnecessary — it is a
 * way to be wrong.
 *
 * ONE function, four callers: the two dialogs decide whether to reveal the field, the schema decides
 * whether to require it, and the action decides whether to send it. All four have to agree, and four
 * copies of one comparison is four things that can drift. It takes the leg's CURRENCY rather than an
 * account because that is what the forms hold — the account picker writes it, and its absence means
 * no account is named, which crosses nothing.
 */
export function legCrossesCurrency(
  legCurrency: string | undefined,
  bucketCurrency: string,
): boolean {
  return !!legCurrency && legCurrency !== bucketCurrency;
}

/*
 * The accounts a caller may attach to their own leg: their own, and active.
 *
 * Active-only mirrors what every other money form offers rather than what the API accepts — an
 * archived account is not somewhere to route a payment that happened. Any currency, because a
 * settlement crossing currencies is the one moment somebody actually agreed a rate, and forbidding it
 * would remove the case the two leg amounts exist for.
 */
export function ownLegAccounts(accounts: Account[]): Account[] {
  return accounts.filter((account) => account.isActive);
}

// --- The section as a whole ---

/*
 * What the balances section says when it has no buckets to show.
 *
 * A fully-settled bucket disappears from the response entirely, so an empty list means one of two
 * opposite things: nothing has been shared yet, or everything that was has been cleared. The first
 * asks for a first entry and the second says there is nothing to do — and showing either sentence in
 * the other's situation is a plain untruth about the group's money.
 *
 * `hasAnyFlow` is BOTH flows, not just spending: a group whose only shared record is a piece of income
 * everyone has already been paid their share of is square, not empty, and telling them to add their
 * first expense would be wrong about a ledger they can see right above.
 */
export type BalancesEmptyState = 'nothingShared' | 'allSquare';

/*
 * Whether the group has recorded any shared flow at all — spending or income.
 *
 * Named rather than asked inline at the call site, because it is the input to the sentence above and
 * an inline copy is a second place the question can be asked with one flow missing. Takes both lists
 * rather than two booleans so a caller cannot pass the same one twice.
 */
export function hasAnySharedFlow(expenses: unknown[], income: unknown[]): boolean {
  return expenses.length > 0 || income.length > 0;
}

export function balancesEmptyState(hasAnyFlow: boolean): BalancesEmptyState {
  return hasAnyFlow ? 'allSquare' : 'nothingShared';
}

/*
 * Whether the group has any open position at all, across every currency. Used to decide whether the
 * section renders buckets or its empty state; never to net anything, which buckets exist so as not
 * to do.
 */
export function hasOpenBalances(buckets: GroupCurrencyBalance[]): boolean {
  return buckets.length > 0;
}

// --- The overpay waterfall ---

/*
 * Whether a plan has anything to confirm.
 *
 * An excess with nowhere to go is not a plan: the payment simply overshoots its own bucket and flips
 * it, which is D30 and needs no confirmation step — the payer typed the number. What needs confirming
 * is money crossing into a currency they did not name, which is what a reachable bucket means.
 *
 * A non-empty bucket list already MEANS there is an excess — the preview returns no buckets at all
 * when the payment does not exceed its own, and none for a currency it has no rate to reach. So
 * re-checking `excess` here would be a second copy of a fact this field already carries, and one that
 * no input could ever disagree with.
 */
export function planNeedsConfirming(plan: GroupSettlementPlan): boolean {
  return plan.buckets.length > 0;
}

/*
 * The rows the plan will write, in the order they will be written.
 *
 * Every figure comes from the API — `primaryAmount` is read, never re-derived from the leftover —
 * because the payer confirms these numbers and then they are recorded. This assembles what the server
 * already decided; it does not decide anything itself.
 *
 * A bucket the excess never reached contributes no row, and neither does a paid bucket the payment
 * covered nothing of (paying purely to clear another currency).
 */
export interface PlannedSettlementRow {
  currency: string;
  amount: string;
}

export function plannedRows(plan: GroupSettlementPlan): PlannedSettlementRow[] {
  const primary =
    Number(plan.primaryAmount) > 0 ? [{ currency: plan.currency, amount: plan.primaryAmount }] : [];
  return [
    ...primary,
    ...plan.buckets
      .filter((bucket) => Number(bucket.amount) > 0)
      .map((bucket) => ({ currency: bucket.currency, amount: bucket.amount })),
  ];
}

/*
 * The currencies a confirm step should send back as kept.
 *
 * Sent explicitly even when every bucket is ticked, rather than relying on the "absent means all"
 * default: between the preview and the confirmation somebody else may have recorded a payment, and an
 * absent field would silently include a bucket that appeared in the meantime. The list is what the
 * payer actually saw.
 */
export function selectedSpilloverCurrencies(plan: GroupSettlementPlan): string[] {
  return plan.buckets.filter((bucket) => bucket.selected).map((bucket) => bucket.currency);
}

/*
 * Whether a bucket was offered but the excess never got to it — ticked, priced, and still untouched.
 *
 * Worth saying on the row rather than leaving it blank: "nothing was applied here" reads as a bug
 * otherwise, when in fact the money simply ran out one bucket earlier.
 */
export function bucketOutOfReach(bucket: GroupSettlementPlanBucket): boolean {
  return bucket.selected && Number(bucket.amount) === 0;
}

// Whether a bucket got only part of what it is owed, which is the one case a row's two figures differ
// for a reason the payer should see rather than wonder about.
export function bucketPartlyCleared(bucket: GroupSettlementPlanBucket): boolean {
  return Number(bucket.amount) > 0 && Number(bucket.amount) < Number(bucket.outstanding);
}
