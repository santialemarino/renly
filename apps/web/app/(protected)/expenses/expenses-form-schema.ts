import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { EXPENSE_CATEGORIES, PAYMENT_METHODS } from '@/lib/constants/categories';

// Cap mirrors the backend (apps/api/app/schemas/expense.py::ExpenseCreate.cycles_to_advance — le=12).
// One year of monthly pre-pay is the realistic upper; prevents typo explosions (60 -> 60 expenses).
export const MAX_CYCLES_TO_ADVANCE = 12;

interface BuildExpenseFormSchemaArgs {
  requiredMsg: string;
  invalidCyclesMsg: string;
}

export function buildExpenseFormSchema({
  requiredMsg,
  invalidCyclesMsg,
}: BuildExpenseFormSchemaArgs) {
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
      // Pre-pay multiple obligation cycles in one Mark Paid click (Phase 3, follow-up Item 2).
      // String-typed because the input is IntegerInput (digit-only string). Empty / undefined
      // means "default to 1" in the action. The 1..12 range is the load-bearing rule — the
      // field is hidden on non-recurring obligations + on non-Mark-Paid flows, so the value
      // only matters when populated through the prefill path.
      cyclesToAdvance: z
        .string()
        .optional()
        .refine(
          (v) => {
            if (v === undefined || v === '') return true;
            if (!/^\d+$/.test(v)) return false;
            const n = Number(v);
            return n >= 1 && n <= MAX_CYCLES_TO_ADVANCE;
          },
          { message: invalidCyclesMsg },
        ),
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
