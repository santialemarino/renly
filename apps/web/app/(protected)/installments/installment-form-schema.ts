import { z } from 'zod';

export function buildInstallmentFormSchema(requiredMsg: string, invalidCountMsg: string) {
  const positiveIntField = z
    .string()
    .min(1, { message: requiredMsg })
    .refine((v) => /^\d+$/.test(v) && Number(v) >= 1, { message: invalidCountMsg });

  return z.object({
    name: z.string().min(1, { message: requiredMsg }).max(255),
    totalAmount: z.string().min(1, { message: requiredMsg }),
    installmentAmount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    installmentsCount: positiveIntField,
    currentInstallment: positiveIntField,
    startDate: z.string().min(1, { message: requiredMsg }),
    paymentMethod: z.enum(['cash', 'debit', 'transfer', 'credit_card']).optional(),
    creditCardId: z.number().optional(),
  });
}

export type InstallmentFormValues = z.infer<ReturnType<typeof buildInstallmentFormSchema>>;
