import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';

export function buildSettlementFormSchema(requiredMsg: string) {
  return z.object({
    date: z.string().min(1, { message: requiredMsg }),
    amount: z.string().min(1, { message: requiredMsg }),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
  });
}

export type SettlementFormValues = z.infer<ReturnType<typeof buildSettlementFormSchema>>;
