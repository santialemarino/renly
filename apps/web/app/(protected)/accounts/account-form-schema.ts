import { z } from 'zod';

import { ACCOUNT_TYPES } from '@/lib/constants/accounts';
import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';

export function buildAccountFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(255),
    type: z.enum(ACCOUNT_TYPES, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    openingBalance: z.string().optional(),
    openingDate: z.string().min(1, { message: requiredMsg }),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
  });
}

export type AccountFormValues = z.infer<ReturnType<typeof buildAccountFormSchema>>;
