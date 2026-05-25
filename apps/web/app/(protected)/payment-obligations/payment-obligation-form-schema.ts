import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { EXPENSE_CATEGORIES } from '@/lib/constants/categories';
import { OBLIGATION_RECURRENCES } from '@/lib/constants/recurrences';

export function buildPaymentObligationFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(255),
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    nextDueDate: z.string().min(1, { message: requiredMsg }),
    recurrence: z.enum(OBLIGATION_RECURRENCES).optional(),
    category: z.string().max(100).optional(),
    expenseCategory: z.enum(EXPENSE_CATEGORIES).optional(),
    paymentMethod: z.enum(['cash', 'debit', 'transfer', 'credit_card']).optional(),
    creditCardId: z.number().optional(),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
  });
}

export type PaymentObligationFormValues = z.infer<
  ReturnType<typeof buildPaymentObligationFormSchema>
>;
