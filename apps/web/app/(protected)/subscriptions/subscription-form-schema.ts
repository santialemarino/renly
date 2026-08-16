import { z } from 'zod';

import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { BILLING_CYCLES } from '@/lib/constants/recurrences';

export function buildSubscriptionFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(255),
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    billingCycle: z.enum(BILLING_CYCLES, { message: requiredMsg }),
    nextBillingDate: z.string().min(1, { message: requiredMsg }),
    paymentMethod: z.enum(PAYMENT_METHODS).optional(),
    creditCardId: z.number().optional(),
    // Optional funding account the scheduler links each emitted charge to (non-card methods only).
    // Nullable so clearing it can round-trip through `null` (AccountField's contract).
    defaultAccountId: z.number().nullable().optional(),
  });
}

export type SubscriptionFormValues = z.infer<ReturnType<typeof buildSubscriptionFormSchema>>;
