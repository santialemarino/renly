import { z } from 'zod';

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
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1), {
        message: messages.maxCollectionsInvalidMsg,
      }),
    collectionWarningPct: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 100), {
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
