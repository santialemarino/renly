import { z } from 'zod';

interface AlertsFormMessages {
  maxGroupsInvalidMsg: string;
  groupWarningPctInvalidMsg: string;
  liquidityThresholdInvalidMsg: string;
}

export function buildAlertsFormSchema(messages: AlertsFormMessages) {
  return z.object({
    maxGroups: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1), {
        message: messages.maxGroupsInvalidMsg,
      }),
    groupWarningPct: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 100), {
        message: messages.groupWarningPctInvalidMsg,
      }),
    liquidityThresholdPct: z
      .string()
      .optional()
      .refine((v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 99), {
        message: messages.liquidityThresholdInvalidMsg,
      }),
  });
}

export type AlertsFormValues = z.infer<ReturnType<typeof buildAlertsFormSchema>>;
