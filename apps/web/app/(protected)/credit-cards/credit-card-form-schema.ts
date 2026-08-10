import { z } from 'zod';

import { CREDIT_CARD_NAME_MAX } from '@/lib/constants/api-constants';

export function buildCreditCardFormSchema(
  requiredMsg: string,
  invalidDayMsg: string,
  invalidMonthlyPaymentMsg: string,
) {
  const dayField = z
    .string()
    .min(1, { message: requiredMsg })
    .refine((v) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 31, {
      message: invalidDayMsg,
    });

  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(CREDIT_CARD_NAME_MAX),
    closingDay: dayField,
    dueDay: dayField,
    currency: z.string().min(1, { message: requiredMsg }),
    monthlyPayment: z
      .string()
      .optional()
      .refine((v) => !v || (!Number.isNaN(Number(v)) && Number(v) >= 0), {
        message: invalidMonthlyPaymentMsg,
      }),
    // Optional funding account that pre-fills a settlement's "Paid from". Nullable so clearing it can
    // round-trip through `null` (AccountField's contract).
    defaultAccountId: z.number().nullable().optional(),
  });
}

export type CreditCardFormValues = z.infer<ReturnType<typeof buildCreditCardFormSchema>>;
