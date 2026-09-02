import type { GroupMember } from '@/lib/api/groups';
import type { SharedExpense, SharedExpenseSplit } from '@/lib/api/shared-expenses';

/*
 * What a shared expense's surface shows and offers, as pure functions over the API's own response.
 *
 * Extracted from the components for the reason `pot-rules.ts` was: these decide which controls render
 * at all, and every one mirrors a rule the API enforces. The API is the real gate — a wrong answer
 * here is a control that 400s rather than a hole — but "offered then refused" is the experience these
 * flows exist to avoid, so the predicates have to agree with the backend exactly.
 *
 * The split's own rules are NOT here: a split is a split whichever direction the money went, so
 * `split-rules.ts` and `split-form-schema.ts` own them and shared income reads the same two modules.
 *
 * Two distinctions carry most of the weight, and conflating either is the mistake to avoid:
 *
 *   * A member's position is TWO figures — what they consumed and what they fronted — and their
 *     balance is the difference. Nothing here ever treats one as the other.
 *   * "Who fronted it" is not always one person. Money from a shared account was fronted by that
 *     pot's owners in their own proportions, which is why there is no payer column and why the API
 *     reports no payer for such an expense however its ownership happens to be divided.
 */

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
