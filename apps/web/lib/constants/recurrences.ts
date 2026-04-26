// Allowed billing cycles for subscriptions (sent as-is to the API).
export const BILLING_CYCLES = ['weekly', 'biweekly', 'monthly', 'quarterly', 'annual'] as const;

export type BillingCycle = (typeof BILLING_CYCLES)[number];
