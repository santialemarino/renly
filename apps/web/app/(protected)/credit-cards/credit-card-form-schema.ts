import { z } from 'zod';

import { CREDIT_CARD_NAME_MAX } from '@/lib/constants/api-constants';

export function buildCreditCardFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(CREDIT_CARD_NAME_MAX),
    closingDay: z.string().min(1, { message: requiredMsg }),
    dueDay: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
  });
}

export type CreditCardFormValues = z.infer<ReturnType<typeof buildCreditCardFormSchema>>;
