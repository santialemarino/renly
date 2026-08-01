import { z } from 'zod';

/*
 * The credited amount is optional here on purpose: within one currency it mirrors the debited amount
 * and the field is hidden, while across currencies the dialog reveals it and marks it required. The
 * currency comparison needs the two accounts, which the schema cannot see, so the API owns the real
 * rule (400 `transfer_amount_required` / `transfer_amounts_must_match`) and the dialog surfaces it.
 */
export function buildTransferFormSchema(requiredMsg: string) {
  return z.object({
    fromAccountId: z.number({ message: requiredMsg }),
    toAccountId: z.number({ message: requiredMsg }),
    date: z.string().min(1, { message: requiredMsg }),
    fromAmount: z.string().min(1, { message: requiredMsg }),
    toAmount: z.string().optional(),
    notes: z.string().optional(),
  });
}

export type TransferFormValues = z.infer<ReturnType<typeof buildTransferFormSchema>>;
