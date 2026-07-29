import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';

export function buildSettlementFormSchema(requiredMsg: string) {
  return z.object({
    date: z.string().min(1, { message: requiredMsg }),
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    // Optional cash/bank account the payment is drawn from — paying a card is a real cash outflow.
    accountId: z.number().nullable().optional(),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
  });
}

export type SettlementFormValues = z.infer<ReturnType<typeof buildSettlementFormSchema>>;
