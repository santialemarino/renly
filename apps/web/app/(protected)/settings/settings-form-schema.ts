import { z } from 'zod';

import { PRESET_PATTERN } from '@/lib/constants/period-presets';

function presetField(invalidMsg: string) {
  return z
    .string()
    .optional()
    .refine((v) => !v || PRESET_PATTERN.test(v), { message: invalidMsg });
}

export function buildSettingsFormSchema(presetInvalidMsg: string) {
  return z.object({
    primaryCurrency: z.string().min(1),
    secondaryCurrency: z.string().nullable().optional(),
    preferredCurrencies: z.string().optional(),
    periodPreset1: presetField(presetInvalidMsg),
    periodPreset2: presetField(presetInvalidMsg),
    periodPreset3: presetField(presetInvalidMsg),
    periodPreset4: presetField(presetInvalidMsg),
    maxGroups: z.string().optional(),
    groupWarningPct: z.string().optional(),
  });
}

export type SettingsFormValues = z.infer<ReturnType<typeof buildSettingsFormSchema>>;
