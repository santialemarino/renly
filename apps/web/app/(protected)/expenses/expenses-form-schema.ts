import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { EXPENSE_CATEGORIES, PAYMENT_METHODS } from '@/lib/constants/categories';

export function buildExpenseFormSchema(requiredMsg: string) {
  return z.object({
    date: z.string().min(1, { message: requiredMsg }),
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    category: z.enum(EXPENSE_CATEGORIES).optional(),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
    paymentMethod: z.enum(PAYMENT_METHODS).optional(),
    creditCardId: z.number().optional(),
    paymentObligationId: z.number().optional(),
  });
}

export type ExpenseFormValues = z.infer<ReturnType<typeof buildExpenseFormSchema>>;
