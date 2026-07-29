import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { INCOME_CATEGORIES } from '@/lib/constants/categories';

export function buildIncomeFormSchema(requiredMsg: string) {
  return z.object({
    date: z.string().min(1, { message: requiredMsg }),
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    category: z.enum(INCOME_CATEGORIES).optional(),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
    accountId: z.number().nullable().optional(),
  });
}

export type IncomeFormValues = z.infer<ReturnType<typeof buildIncomeFormSchema>>;
