// Allowed billing cycles for subscriptions (sent as-is to the API).
export const BILLING_CYCLES = ['weekly', 'biweekly', 'monthly', 'quarterly', 'annual'] as const;

export type BillingCycle = (typeof BILLING_CYCLES)[number];

// Recurrence options for payment obligations. Empty string is the form-level
// representation of "one-off" (null on the API).
export const OBLIGATION_RECURRENCES = ['monthly', 'bimonthly', 'quarterly', 'annual'] as const;

export type ObligationRecurrence = (typeof OBLIGATION_RECURRENCES)[number];
