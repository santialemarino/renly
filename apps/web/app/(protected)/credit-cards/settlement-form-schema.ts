import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';

export function buildSettlementFormSchema(requiredMsg: string) {
  return z.object({
    date: z.string().min(1, { message: requiredMsg }),
    // The CARD leg: what the payment clears off the bucket.
    amount: z.string().min(1, { message: requiredMsg }),
    currency: z.string().min(1, { message: requiredMsg }),
    // Optional cash/bank account the payment is drawn from — paying a card is a real cash outflow.
    accountId: z.number().nullable().optional(),
    /*
     * The CASH leg: what left that account, in ITS currency. Optional here because whether it is
     * required depends on the chosen ACCOUNT's currency, which this builder never sees — the dialog
     * knows it and raises an inline error on submit, and the API refuses with
     * `settlement_account_amount_required` as the real guard.
     */
    accountAmount: z.string().optional(),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
  });
}

export type SettlementFormValues = z.infer<ReturnType<typeof buildSettlementFormSchema>>;
