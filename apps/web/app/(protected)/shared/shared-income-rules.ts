import type { GroupMember } from '@/lib/api/groups';
import type { SharedIncome, SharedIncomeSplit } from '@/lib/api/shared-income';
import type { IncomeDestination } from '@/lib/constants/shared-income';

/*
 * What a shared-income surface shows and offers, as pure functions over the API's own response.
 *
 * Extracted from the components for the reason `shared-expense-rules.ts` was: these decide which
 * controls render at all, and every one mirrors a rule the API enforces. The API is the real gate — a
 * wrong answer here is a control that 400s rather than a hole — but "offered then refused" is the
 * experience these flows exist to avoid, so the predicates have to agree with the backend exactly.
 *
 * Two distinctions carry most of the weight, and conflating either is the mistake to avoid:
 *
 *   * A member's position is TWO figures — what they are entitled to and what actually reached them —
 *     and their balance is the difference. Nothing here ever treats one as the other.
 *   * "Who holds it" is not always one person. Money that arrived in a shared account reached that
 *     pot's owners in their own proportions, which is why there is no receiver column and why the API
 *     reports no recipient for a joint row however its ownership happens to be divided.
 *
 * The split's own rules are NOT restated here: income divides by the same four methods and reopens
 * with the same losses, so `split-rules.ts` owns them and the form imports from there directly.
 */

// --- Where the money went ---

/*
 * Whether this row stayed joint, which is exactly what the stored destination says.
 *
 * Read off `destination` and never inferred — not from the account being a pot's (the client cannot
 * see that), and not from the split shape either, because a pot with exactly one owner has that owner
 * receiving the whole amount, which is indistinguishable from one person collecting it. Reading it any
 * other way reproduces the defect 5a fixed on the expense side.
 */
export function isJointlyHeld(income: SharedIncome): boolean {
  return income.destination === 'joint';
}

/*
 * What the "went to" cell states, as a case rather than a nested ternary in the row.
 *
 * `joint` carries the account's name when there is one to carry, so the cell says which shared account
 * rather than only that it stayed together. The name can still be absent — a private account belonging
 * to another member is hidden from this caller by the policies, and the response then carries the id
 * without the name — in which case there is nothing honest to add.
 *
 * Returns the figures rather than only a tag, so the caller formats what the rule selected instead of
 * re-checking the same nulls to satisfy the type.
 */
export type IncomeHolderDisplay =
  | { kind: 'joint'; accountName: string | null }
  | { kind: 'member'; displayName: string };

export function incomeHolderDisplay(income: SharedIncome): IncomeHolderDisplay {
  if (isJointlyHeld(income)) {
    return { kind: 'joint', accountName: income.paidToAccountName };
  }
  // Non-null by construction: the API derives the name from the same seat it derives the id from.
  return { kind: 'member', displayName: income.receivedByDisplayName ?? '—' };
}

/*
 * Whether the form may ask WHERE the money landed — an account of the recipient's own.
 *
 * Only for the viewer's own seat, and the API is what makes that so: an account named here must belong
 * to the recipient, and the row-level policies hide every other member's from this caller entirely.
 * Recording that somebody else collected the money can only ever be a note that they did, so offering
 * the picker would produce a 404 naming an account the user can genuinely see nowhere.
 *
 * The same rule `canNameOwnInstrument` carries on the expense side, kept as its own function rather
 * than shared with it: the two happen to compare the same shapes today, and they are about different
 * fields on different forms — a change to one has no business moving the other.
 */
export function canNameOwnDestination(
  receivedByMemberId: number | null,
  mySeatId: number | null,
): boolean {
  return mySeatId !== null && receivedByMemberId === mySeatId;
}

// --- F1: the default split ---

/*
 * The split the form pre-fills for a source asset: that asset's pot's ownership proportions (F1).
 *
 * PERCENTAGES keyed by seat, because that is what the pot itself reports and what sums to exactly
 * 100 — the API refuses a percentage split that misses it, and the pot's own figures are already
 * remainder-corrected to reach it. Deriving amounts here instead would round a second time.
 *
 * `missingOwners` is what makes this safe to apply, and it is not a theoretical case. A member who
 * LEAVES the group keeps any pot units they hold — the design supports that deliberately, and the
 * expense side relies on it — but a departed seat is not offered as a participant. Pre-filling the
 * remaining owners alone would hand the user percentages summing to 60 and a submit refused with "the
 * percentages add up to 60%, not 100%", through no fault of theirs. So the shares come back ONLY when
 * every owner still has a seat to put them on, and the caller says whose absence stopped it rather
 * than silently doing nothing.
 *
 * Rescaling the remainder onto the owners who are left is the one thing this must never do: it would
 * invent a division nobody agreed, on the screen where people check each other's numbers.
 *
 * An empty result with no missing owners is the third state — the pot has no ownership on record at
 * all — and the caller falls back to the group's agreed default method, which is what a group with
 * nothing divided yet should get.
 *
 * ▸ It is the FORM's default and nothing more. What the API stores is the split the request states, so
 * a later change to who owns the asset never restates income the group already agreed on — the same
 * reason the ownership proportions behind a joint row are pinned at write time rather than derived.
 */
export interface OwnershipDefault {
  shares: Map<number, string>;
  // Seat ids that own part of the asset but have no row in the split editor. Non-empty means the
  // caller must NOT apply `shares`, which is why it comes back empty in that case.
  missingOwners: number[];
}

export function ownershipDefaultShares(
  shares: { memberId: number; percentage: string }[],
  seatIds: number[],
): OwnershipDefault {
  const owners = shares.filter((share) => Number(share.percentage) > 0);
  const offered = new Set(seatIds);
  const missingOwners = owners
    .map((share) => share.memberId)
    .filter((memberId) => !offered.has(memberId));
  if (missingOwners.length > 0) return { shares: new Map(), missingOwners };
  return {
    shares: new Map(owners.map((share) => [share.memberId, share.percentage])),
    missingOwners: [],
  };
}

/*
 * The display names of seats the roster holds, for a list of ids. Used to say WHOSE absence stopped an
 * F1 pre-fill — the roster includes former members, which is exactly why it can answer.
 *
 * Falls back to nothing rather than a placeholder for an id the roster does not hold: that would be a
 * seat from another group, which is a different problem and not one this sentence should describe.
 */
export function seatNames(memberIds: number[], members: GroupMember[]): string[] {
  const byId = new Map(members.map((member) => [member.id, member]));
  return memberIds
    .map((id) => byId.get(id))
    .filter((member): member is GroupMember => member !== undefined)
    .map((member) => member.displayName);
}

/*
 * The destination this source was last recorded with (F2's "remembered per-source default").
 *
 * Derived from the group's own income list rather than stored anywhere, which is what "remembered"
 * means: it always reflects what the user actually did last, it cannot go stale against their
 * behaviour, and it needs no column that would have no correct value before the first entry.
 *
 * Matches on the source asset, INCLUDING the no-source case — somebody who records untied income the
 * same way every month gets the same benefit as somebody with a property. The list arrives newest
 * first from the API, so the first match is the most recent; `find` rather than a sort keeps that
 * dependency in one place and this function honest about it.
 *
 * Returns null when this source has never been recorded, and the caller picks the opening default.
 */
export function rememberedDestination(
  history: SharedIncome[],
  sourceInvestmentId: number | null,
): IncomeDestination | null {
  const previous = history.find((row) => row.sourceInvestmentId === sourceInvestmentId);
  return previous?.destination ?? null;
}

// --- Participants ---

/*
 * The names of any seats a request would name that are no longer active — participants or the
 * recipient.
 *
 * The API refuses these (404 "Group member not found"), and this is one of the few places worth
 * mirroring a backend rule rather than letting the refusal happen: that answer carries no error code,
 * so it would reach a Spanish reader in English, and it is reachable through no fault of the user. A
 * member can only be removed once they are square, which leaves every row that named them behind — so
 * opening one of those for an unrelated edit is how somebody meets this.
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

// --- Reopening a saved row ---

/*
 * Whether a stored split row belongs to somebody entitled to a SHARE of the income, as opposed to
 * somebody who only collected it.
 *
 * A split row is written for anyone entitled to something, holding something, or both — so the one
 * shape that is not a participant is a row entitled to nothing while holding something: a custodian
 * who collected the rent and takes no share of it, the mirror of a payer who took no part in a bill.
 *
 * A row of two zeros IS a participant: an `exact` split may deliberately give somebody nothing, and
 * that is a person who was included rather than one who was not.
 */
export function wasParticipant(split: SharedIncomeSplit): boolean {
  return !(Number(split.amount) === 0 && Number(split.receivedAmount) > 0);
}

/*
 * Whether the group has recorded any shared income at all, which is what tells an empty section apart
 * from a settled one — the same distinction `hasSharedSpending` draws on the way out.
 */
export function hasSharedIncome(income: SharedIncome[]): boolean {
  return income.length > 0;
}
