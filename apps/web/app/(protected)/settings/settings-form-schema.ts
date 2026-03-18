import { z } from 'zod';

export const settingsFormSchema = z.object({
  primaryCurrency: z.string().min(1),
  secondaryCurrency: z.string().nullable().optional(),
});

export type SettingsFormValues = z.infer<typeof settingsFormSchema>;
