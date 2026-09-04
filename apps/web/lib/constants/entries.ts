/*
 * Which table a row of a unioned ENTRY list came from — one type for both lists, because it is one
 * fact. 'private' is the user's own `expense_entries` / `income_entries` row; 'shared' is their SHARE
 * of one their group recorded, read in by that list's union.
 *
 * It is half the row's identity rather than a label: ids are unique per table and NOT across them, so
 * a shared row's id means nothing to `/expenses/{id}` or `/income/{id}`, and every row action has to
 * gate on this. A union type rather than a bare string so a typo in that gate is a type error rather
 * than a silent `false` — which would put Edit and Delete back on a row that acts on somebody else's
 * money.
 */
export const ENTRY_SCOPES = ['private', 'shared'] as const;

export type EntryScope = (typeof ENTRY_SCOPES)[number];

/*
 * WHICH KIND of entry is being recorded — money going out, or money coming in.
 *
 * A named pair rather than a boolean because it selects a whole FORM, not a flag on one: an expense
 * and a piece of income live in different tables, have different categories and different fields, so
 * the global quick-add's type control swaps which form is on screen exactly the way the scope control
 * beside it does. A union type so a typo in that swap is a type error rather than a silent fall-through
 * to the other list.
 */
export const ENTRY_TYPES = ['expense', 'income'] as const;

export type EntryType = (typeof ENTRY_TYPES)[number];
