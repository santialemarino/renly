// Account types offered in the account form (matches the API `account_type` enum). Display order.
export const ACCOUNT_TYPES = ['cash', 'bank', 'wallet', 'other'] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];

/*
 * Kinds of movement that reach an account, in the ledger filter's display order (matches the API's
 * `MovementKind`). Lives here rather than beside the ledger's fetcher because the filter is a client
 * component and `lib/api/*` is server-only — importing a runtime value from there breaks the build.
 */
export const MOVEMENT_KINDS = [
  'income',
  'expense',
  'transfer',
  'settlement',
  'adjustment',
] as const;

export type MovementKind = (typeof MOVEMENT_KINDS)[number];

/*
 * Which table a movement came from — what actually IDENTIFIES a ledger row. `MovementKind` cannot:
 * `adjustment` spans income and expense, whose id sequences are independent, so two adjustments can
 * share (kind, sourceId). A type rather than an array because nothing enumerates it at runtime.
 */
export type MovementSource = 'income' | 'expense' | 'settlement' | 'transfer';
