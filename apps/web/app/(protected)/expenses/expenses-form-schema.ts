import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { EXPENSE_CATEGORIES, PAYMENT_METHODS } from '@/lib/constants/categories';

export function buildExpenseFormSchema(requiredMsg: string) {
  return z
    .object({
      date: z.string().min(1, { message: requiredMsg }),
      amount: z.string().min(1, { message: requiredMsg }),
      currency: z.string().min(1, { message: requiredMsg }),
      category: z.enum(EXPENSE_CATEGORIES).optional(),
      notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
      paymentMethod: z.enum(PAYMENT_METHODS).optional(),
      creditCardId: z.number().optional(),
      paymentObligationId: z.number().optional(),
      subscriptionId: z.number().optional(),
      installmentId: z.number().optional(),
    })
    .superRefine((values, ctx) => {
      // Mutual exclusivity (Phase 3, follow-up 3a): an expense pays at most one
      // commitment-type. The dropdowns enforce this at click-time by clearing the
      // siblings on change, but a Zod gate is the load-bearing guardrail when the
      // form is submitted programmatically or via prefill.
      const linkCount = [
        values.paymentObligationId,
        values.subscriptionId,
        values.installmentId,
      ].filter((v) => v !== undefined).length;
      if (linkCount > 1) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'linkedCommitmentExclusivity',
          path: ['subscriptionId'],
        });
      }
    });
}

export type ExpenseFormValues = z.infer<ReturnType<typeof buildExpenseFormSchema>>;
