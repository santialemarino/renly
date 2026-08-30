// Account types offered in the account form (matches the API `account_type` enum). Display order.
export const ACCOUNT_TYPES = ['cash', 'bank', 'wallet', 'other'] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];

/*
 * Kinds of movement that reach an account, in the ledger filter's display order (matches the API's
 * `MovementKind`). Lives here rather than beside the ledger's fetcher because the filter is a client
 * component and `lib/api/*` is server-only — importing a runtime value from there breaks the build.
 *
 * `settlement` is a CARD bill and `group_settlement` a shared balance between people. Two kinds rather
 * than one because they are different activities to filter by, and because one kind covering both
 * would make either label a lie about half its rows.
 *
 * `ownership` is money crossing a SCOPE boundary — into a co-owned pot or back out of it. Neither an
 * expense (net worth does not change) nor a transfer (which is neutral only within one scope), so the
 * direction is the sign and the counterparty names the pot.
 */
export const MOVEMENT_KINDS = [
  'income',
  'expense',
  'transfer',
  'settlement',
  'group_settlement',
  'ownership',
  'adjustment',
] as const;

export type MovementKind = (typeof MOVEMENT_KINDS)[number];

/*
 * Which table a movement came from — what actually IDENTIFIES a ledger row. `MovementKind` cannot:
 * `adjustment` spans income and expense, whose id sequences are independent, so two adjustments can
 * share (kind, sourceId). A type rather than an array because nothing enumerates it at runtime.
 *
 * `shared_expense` is the one source with no kind of its own: from the ACCOUNT's point of view a
 * group's dinner is an expense like any other, so it reads as that kind and only the source says the
 * money was a group's.
 */
export type MovementSource =
  | 'income'
  | 'expense'
  | 'shared_expense'
  | 'settlement'
  | 'group_settlement'
  | 'ownership'
  | 'transfer';
