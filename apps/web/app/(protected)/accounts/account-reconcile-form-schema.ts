import { z } from 'zod';

export function buildAccountReconcileFormSchema(requiredMsg: string) {
  return z.object({
    asOfDate: z.string().min(1, { message: requiredMsg }),
    statementBalance: z.string().min(1, { message: requiredMsg }),
  });
}

export type AccountReconcileFormValues = z.infer<
  ReturnType<typeof buildAccountReconcileFormSchema>
>;
