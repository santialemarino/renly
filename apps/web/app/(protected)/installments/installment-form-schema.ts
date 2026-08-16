import { z } from 'zod';

import { PAYMENT_METHODS } from '@/lib/constants/categories';

interface BuildInstallmentFormSchemaArgs {
  requiredMsg: string;
  invalidCountMsg: string;
  interestMustBePositiveMsg: string;
}

export function buildInstallmentFormSchema({
  requiredMsg,
  invalidCountMsg,
  interestMustBePositiveMsg,
}: BuildInstallmentFormSchemaArgs) {
  const positiveIntField = z
    .string()
    .min(1, { message: requiredMsg })
    .refine((v) => /^\d+$/.test(v) && Number(v) >= 1, { message: invalidCountMsg });

  return z
    .object({
      name: z.string().min(1, { message: requiredMsg }).max(255),
      hasInterest: z.boolean(),
      originalPrice: z.string().optional(),
      installmentAmount: z.string().min(1, { message: requiredMsg }),
      currency: z.string().min(1, { message: requiredMsg }),
      installmentsCount: positiveIntField,
      currentInstallment: positiveIntField,
      startDate: z.string().min(1, { message: requiredMsg }),
      paymentMethod: z.enum(PAYMENT_METHODS).optional(),
      creditCardId: z.number().optional(),
      // Optional funding account the scheduler links each emitted charge to (non-card methods only).
      // Nullable so clearing it can round-trip through `null` (AccountField's contract).
      defaultAccountId: z.number().nullable().optional(),
    })
    .superRefine((values, ctx) => {
      if (!values.hasInterest) return;

      const original = values.originalPrice?.trim();
      if (!original) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['originalPrice'],
          message: requiredMsg,
        });
        return;
      }

      const originalNum = Number(original);
      const installmentNum = Number(values.installmentAmount);
      const countNum = Number(values.installmentsCount);
      if (
        Number.isFinite(originalNum) &&
        Number.isFinite(installmentNum) &&
        Number.isFinite(countNum) &&
        installmentNum * countNum <= originalNum
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['originalPrice'],
          message: interestMustBePositiveMsg,
        });
      }
    });
}

export type InstallmentFormValues = z.infer<ReturnType<typeof buildInstallmentFormSchema>>;
