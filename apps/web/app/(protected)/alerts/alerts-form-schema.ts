import { z } from 'zod';

import { COLLECTION_WARNING_PCT_RANGE, MAX_COLLECTIONS_RANGE } from '@/lib/constants/collections';

// A blank field, or a whole number inside the inclusive range.
function blankOrIntWithin(value: string | undefined, [min, max]: readonly [number, number]) {
  if (!value) return true;
  const n = Number(value);
  return Number.isInteger(n) && n >= min && n <= max;
}

interface AlertsFormMessages {
  maxCollectionsInvalidMsg: string;
  collectionWarningPctInvalidMsg: string;
  liquidityThresholdInvalidMsg: string;
  savingsRateInvalidMsg: string;
  incomeExpenseRatioInvalidMsg: string;
}

export function buildAlertsFormSchema(messages: AlertsFormMessages) {
  return z.object({
    maxCollections: z
      .string()
      .optional()
      .refine((v) => blankOrIntWithin(v, MAX_COLLECTIONS_RANGE), {
        message: messages.maxCollectionsInvalidMsg,
      }),
    collectionWarningPct: z
      .string()
      .optional()
      .refine((v) => blankOrIntWithin(v, COLLECTION_WARNING_PCT_RANGE), {
        message: messages.collectionWarningPctInvalidMsg,
      }),
    liquidityThresholdPct: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 99), {
        message: messages.liquidityThresholdInvalidMsg,
      }),
    savingsRateHealthyPct: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 99), {
        message: messages.savingsRateInvalidMsg,
      }),
    savingsRateModeratePct: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 99), {
        message: messages.savingsRateInvalidMsg,
      }),
    incomeExpenseRatioHealthy: z
      .string()
      .optional()
      .refine((v) => !v || (!Number.isNaN(Number(v)) && Number(v) >= 0.1 && Number(v) <= 10), {
        message: messages.incomeExpenseRatioInvalidMsg,
      }),
  });
}

export type AlertsFormValues = z.infer<ReturnType<typeof buildAlertsFormSchema>>;
