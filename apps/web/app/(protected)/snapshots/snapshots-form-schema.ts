import { z } from 'zod';

export const TRANSACTION_TYPES = ['deposit', 'buy', 'sell', 'withdrawal'] as const;
export const TRANSACTION_TYPES_OUTGOING = ['sell', 'withdrawal'] as const;

// existingYearMonths: set of "YYYY-MM" strings for months that already have a snapshot.
// Only validated when adding (not editing).
export function buildSnapshotFormSchema(
  requiredMsg: string,
  duplicateMsg: string,
  existingYearMonths: Set<string>,
  isEdit: boolean,
) {
  return z
    .object({
      date: z
        .string()
        .min(1, requiredMsg)
        .refine(
          (val) => {
            if (isEdit || !val) return true;
            const ym = val.slice(0, 7);
            return !existingYearMonths.has(ym);
          },
          { message: duplicateMsg },
        ),
      value: z.string().min(1, requiredMsg),
      quantity: z.string().optional(),
      includeTransaction: z.boolean(),
      transactionAmount: z.string().optional(),
      transactionQuantity: z.string().optional(),
      transactionType: z.enum(TRANSACTION_TYPES).optional(),
    })
    .superRefine((values, ctx) => {
      // A checked "include transaction" with an empty amount used to silently save NO
      // transaction → invested capital understated, TWR/IRR overstated (audit §3). Require
      // the amount whenever the checkbox is on.
      if (values.includeTransaction && !values.transactionAmount?.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['transactionAmount'],
          message: requiredMsg,
        });
      }
    });
}

export type SnapshotFormValues = z.infer<ReturnType<typeof buildSnapshotFormSchema>>;
