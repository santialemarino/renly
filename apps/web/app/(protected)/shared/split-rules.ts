import { SPLIT_METHODS_WITH_TOTAL, type SplitMethod } from '@/lib/constants/shared-expenses';

/*
 * How a shared amount is divided, as pure functions over the method and over a stored row.
 *
 * Its own module rather than a section of either flow's rules, because a split is a split: a shared
 * expense and a piece of shared income divide by the same four methods, store the same shape, and
 * reopen with the same losses. The API made the same call — `compute_shares` lives in
 * `domain/shared_flow.py` rather than beside the expenses that were its first consumer.
 */

// --- The split method's shape ---

/*
 * Whether the editor can check the figures add up before submitting. Only `exact` and `percentage`
 * have a target — the row's amount and 100 respectively, neither ever rescaled. `shares` are relative
 * weights with nothing to hit, and `equal` takes no figures at all.
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

// --- Reopening a saved split ---

/*
 * The minimum a saved row has to carry for the two functions below. Structural rather than either
 * flow's row type, so a shared expense and a piece of shared income both satisfy it without either
 * module knowing about the other.
 */
export interface SplitBearingRow {
  splitMethod: SplitMethod;
}

/*
 * Which split method the edit form opens a saved row on.
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
export function reopenSplitMethod(row: SplitBearingRow): SplitMethod {
  return row.splitMethod === 'percentage' ? 'exact' : row.splitMethod;
}

/*
 * Whether reopening changed the method, which is the only case the dialog has anything to explain.
 * Derived from the same function that does the changing, so the notice cannot outlive the rule.
 */
export function reopenChangedMethod(row: SplitBearingRow): boolean {
  return reopenSplitMethod(row) !== row.splitMethod;
}
