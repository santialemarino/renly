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
