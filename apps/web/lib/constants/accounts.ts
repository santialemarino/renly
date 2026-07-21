// Account types offered in the account form (matches the API `account_type` enum). Display order.
export const ACCOUNT_TYPES = ['cash', 'bank', 'wallet', 'other'] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];
