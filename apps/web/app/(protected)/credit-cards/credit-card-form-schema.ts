import { z } from 'zod';

import { CREDIT_CARD_NAME_MAX } from '@/lib/constants/api-constants';

export function buildCreditCardFormSchema(requiredMsg: string, invalidDayMsg: string) {
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
  });
}

export type CreditCardFormValues = z.infer<ReturnType<typeof buildCreditCardFormSchema>>;
