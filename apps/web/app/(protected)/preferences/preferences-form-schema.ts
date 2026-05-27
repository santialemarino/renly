import { z } from 'zod';

import { PRESET_PATTERN } from '@/lib/constants/period-presets';

function presetField(invalidMsg: string) {
  return z
    .string()
    .optional()
    .refine((v) => !v || PRESET_PATTERN.test(v), { message: invalidMsg });
}

interface SettingsFormMessages {
  presetInvalidMsg: string;
}

export function buildSettingsFormSchema(messages: SettingsFormMessages) {
  return z.object({
    primaryCurrency: z.string().min(1),
    secondaryCurrency: z.string().nullable().optional(),
    preferredCurrencies: z.string().optional(),
    periodPreset1: presetField(messages.presetInvalidMsg),
    periodPreset2: presetField(messages.presetInvalidMsg),
    periodPreset3: presetField(messages.presetInvalidMsg),
    periodPreset4: presetField(messages.presetInvalidMsg),
    dollarRatePreference: z.string().optional(),
  });
}

export type SettingsFormValues = z.infer<ReturnType<typeof buildSettingsFormSchema>>;
