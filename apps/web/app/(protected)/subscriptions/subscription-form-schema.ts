import { z } from 'zod';

import { BILLING_CYCLES } from '@/lib/constants/recurrences';

export function buildSubscriptionFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(255),
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    billingCycle: z.enum(BILLING_CYCLES, { message: requiredMsg }),
    nextBillingDate: z.string().min(1, { message: requiredMsg }),
    paymentMethod: z.enum(['cash', 'debit', 'transfer', 'credit_card']).optional(),
    creditCardId: z.number().optional(),
  });
}

export type SubscriptionFormValues = z.infer<ReturnType<typeof buildSubscriptionFormSchema>>;
