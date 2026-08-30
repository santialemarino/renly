// Tolerance window (in days) for the manual-dupe expense warning (Phase 3, Step D).
// When the user is entering a manual credit-card expense, the form looks up
// auto-generated expenses (subscription / installment scheduler output) within
// ±DUPE_MATCH_WINDOW_DAYS that match on card / currency / exact amount and shows
// a soft confirmation dialog. Backend mirrors this value in expense_service.py.
export const DUPE_MATCH_WINDOW_DAYS = 15;

/*
 * Which table a row of the expenses list came from. 'private' is the user's own `expense_entries`
 * row; 'shared' is their SHARE of one their group recorded, read in by the list's union.
 *
 * It is half the row's identity rather than a label: ids are unique per table and NOT across them, so
 * a shared row's id means nothing to `/expenses/{id}` and every row action has to gate on this. A
 * union type rather than a bare string so a typo in that gate is a type error rather than a silent
 * `false` — which would put Edit and Delete back on a row that acts on someone else's expense.
 */
export const EXPENSE_SCOPES = ['private', 'shared'] as const;

export type ExpenseScope = (typeof EXPENSE_SCOPES)[number];
