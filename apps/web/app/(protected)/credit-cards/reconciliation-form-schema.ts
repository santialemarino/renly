import { z } from 'zod';

export function buildReconciliationFormSchema(requiredMsg: string) {
  return z.object({
    currency: z.string().min(1, { message: requiredMsg }),
    periodStart: z.string().min(1, { message: requiredMsg }),
    periodEnd: z.string().min(1, { message: requiredMsg }),
    statementBalance: z.string().min(1, { message: requiredMsg }),
  });
}

export type ReconciliationFormValues = z.infer<ReturnType<typeof buildReconciliationFormSchema>>;
