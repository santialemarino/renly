import type { GroupMember } from '@/lib/api/groups';
import type { SharedExpense, SharedExpenseSplit } from '@/lib/api/shared-expenses';
import { SPLIT_METHODS_WITH_TOTAL, type SplitMethod } from '@/lib/constants/shared-expenses';

/*
 * What a shared expense's surface shows and offers, as pure functions over the API's own response.
 *
 * Extracted from the components for the reason `pot-rules.ts` was: these decide which controls render
 * at all, and every one mirrors a rule the API enforces. The API is the real gate — a wrong answer
 * here is a control that 400s rather than a hole — but "offered then refused" is the experience these
 * flows exist to avoid, so the predicates have to agree with the backend exactly.
 *
 * Two distinctions carry most of the weight, and conflating either is the mistake to avoid:
 *
 *   * A member's position is TWO figures — what they consumed and what they fronted — and their
 *     balance is the difference. Nothing here ever treats one as the other.
 *   * "Who fronted it" is not always one person. Money from a shared account was fronted by that
 *     pot's owners in their own proportions, which is why there is no payer column and why the API
 *     reports no payer for such an expense however its ownership happens to be divided.
 */

// --- The split method's shape ---

/*
 * Whether the editor can check the figures add up before submitting. Only `exact` and `percentage`
 * have a target — the expense's amount and 100 respectively, neither ever rescaled. `shares` are
 * relative weights with nothing to hit, and `equal` takes no figures at all.
 */
export function splitMethodHasTotal(method: SplitMethod): boolean {
  return SPLIT_METHODS_WITH_TOTAL.includes(method);
}

/*
 * Which figure each participant supplies, or null when the method asks for none.
 *
 * ONE function rather than a "does it take figures" boolean beside a "which unit" switch, because
 * the same answer decides four things that must never disagree: whether the figure inputs render at
 * all, what each is labelled, what precision it takes, and which rule the editor states when the
 * figures do not satisfy the method. Two derivations of that would be two things that can drift, and
 * a pair of booleans would additionally admit a state — percentage AND shares — that cannot exist.
 *
 * `equal` is the null: it divides by head count, so there is nothing to type and nothing to get
 * wrong. Returned as a case rather than left to the call site because the alternative is indexing a
 * translation namespace with a method that has no entry there — a key lookup that only fails in a
 * state nobody can reach, which is exactly the kind that ships.
 */
export type SplitFigureKind = 'exact' | 'shares' | 'percentage';

export function splitFigureKind(method: SplitMethod): SplitFigureKind | null {
  return method === 'equal' ? null : method;
}

// --- Who fronted it ---

/*
 * Whether joint money fronted this expense, which is exactly what a null payer MEANS on the response.
 *
 * Not inferred from the account being a pot's (the client cannot see that) and not inferred from the
 * split shape either — a pot with exactly one owner has that owner fronting the whole amount, which
 * is indistinguishable from somebody paying out of their own pocket. The API decides it by the
 * funding and says so in this one field; reading it any other way reproduces the defect 5a fixed.
 */
export function isJointlyFunded(expense: SharedExpense): boolean {
  return expense.payerMemberId === null;
}

/*
 * Whether the form may ask HOW the payer paid — a payment method, a card, an account.
 *
 * Only for the viewer's own seat, and the API is what makes that so: a card or an account named here
 * must belong to the payer, and the row-level policies hide every other member's from this caller
 * entirely. Recording that somebody else paid can only ever be a note that they did, so offering the
 * pickers would produce a 404 naming an account the user can genuinely see nowhere.
 *
 * Never for joint money: nobody's instrument paid, the shared account did.
 */
export function canNameOwnInstrument(
  payerMemberId: number | null,
  mySeatId: number | null,
): boolean {
  return mySeatId !== null && payerMemberId === mySeatId;
}

// --- Participants ---

/*
 * The names of any seats a request would name that are no longer active — participants or the payer.
 *
 * The API refuses these (404 "Group member not found"), and this is one of the few places worth
 * mirroring a backend rule rather than letting the refusal happen: that answer carries no error code,
 * so it would reach a Spanish reader in English, and it is reachable through no fault of the user.
 * A member can only be removed once they are square, which leaves every expense that named them
 * behind — so opening one of those for an unrelated edit is how somebody meets this.
 *
 * Returns names rather than ids because the only thing the form can do with the answer is say which
 * people it is about.
 */
export function inactiveSeatNames(memberIds: number[], members: GroupMember[]): string[] {
  const byId = new Map(members.map((member) => [member.id, member]));
  return memberIds
    .map((id) => byId.get(id))
    .filter((member): member is GroupMember => member !== undefined && !member.isActive)
    .map((member) => member.displayName);
}

// --- Rows ---

/*
 * What the "paid by" cell states, as a case rather than a nested ternary in the row.
 *
 * `joint` carries the account's name when there is one to carry, so the cell says which shared
 * account rather than only that it was shared. The name can still be absent — a private account
 * belonging to another member is hidden from this caller by the policies, and the response then
 * carries the id without the name — in which case there is nothing honest to add.
 *
 * Returns the figures rather than only a tag, so the caller formats what the rule selected instead of
 * re-checking the same nulls to satisfy the type.
 */
export type ExpensePayerDisplay =
  | { kind: 'joint'; accountName: string | null }
  | { kind: 'member'; displayName: string };

export function expensePayerDisplay(expense: SharedExpense): ExpensePayerDisplay {
  if (isJointlyFunded(expense)) {
    return { kind: 'joint', accountName: expense.paidFromAccountName };
  }
  // Non-null by construction: the API derives the name from the same seat it derives the id from.
  return { kind: 'member', displayName: expense.payerDisplayName ?? '—' };
}

// --- Reopening a saved expense ---

/*
 * Whether a stored split row belongs to somebody who took PART in the expense, as opposed to somebody
 * who only fronted money for it.
 *
 * A split row is written for anyone who consumed something, fronted something, or both — so the one
 * shape that is not a participant is a row that consumed nothing while fronting something: a payer
 * who was not in on the bill (D33), or a pot owner whose joint account paid for a meal they missed.
 *
 * A row of two zeros IS a participant: an `exact` split may deliberately give somebody nothing, and
 * that is a person who was there rather than one who was not.
 */
export function wasParticipant(split: SharedExpenseSplit): boolean {
  return !(Number(split.amount) === 0 && Number(split.paidAmount) > 0);
}

/*
 * Which split method the edit form opens a saved expense on.
 *
 * The stored row keeps the METHOD and the resulting amounts, never the figures that produced them —
 * so reopening has to reconstruct the division from the amounts alone, and only three of the four
 * methods can be reconstructed from them exactly:
 *
 *   * `equal` needs no figures at all and re-divides identically.
 *   * `exact` figures ARE the amounts.
 *   * `shares` taken as the amounts themselves are weights in exactly the stored proportion, so the
 *     division comes out unchanged to the cent.
 *   * `percentage` cannot. Dividing each amount by the total recovers percentages that need not sum
 *     to 100 — three equal shares of 3.00 come back as 33.33 three times, which is 99.99 — so the
 *     form would open already refused, through no fault of whoever opened it. Rounding the residue
 *     onto somebody would be inventing a figure they never chose, on the one screen where people
 *     check each other's numbers.
 *
 * So a percentage split reopens as EXACT AMOUNTS: the one lossless statement of what was actually
 * agreed. The dialog says so rather than letting the method appear to have changed by itself.
 */
export function reopenSplitMethod(expense: SharedExpense): SplitMethod {
  return expense.splitMethod === 'percentage' ? 'exact' : expense.splitMethod;
}

/*
 * Whether reopening changed the method, which is the only case the dialog has anything to explain.
 * Derived from the same function that does the changing, so the notice cannot outlive the rule.
 */
export function reopenChangedMethod(expense: SharedExpense): boolean {
  return reopenSplitMethod(expense) !== expense.splitMethod;
}

/*
 * Whether the group has anything shared at all, which is what tells an empty balances section apart
 * from a settled one.
 *
 * A fully-settled bucket disappears from the balances response entirely, so "no buckets" alone cannot
 * distinguish "nobody has recorded anything" from "everyone is square" — two states that deserve
 * opposite sentences, one an invitation and one a reassurance.
 */
export function hasSharedSpending(expenses: SharedExpense[]): boolean {
  return expenses.length > 0;
}
