import { z } from 'zod';

import { TIMEZONE_MODES } from '@/lib/constants/timezones';
import { LANGUAGE_MODES, SUPPORTED_LOCALES } from '@/lib/i18n/locales';

export const localizationFormSchema = z.object({
  timezone: z.string().min(1),
  timezoneMode: z.enum(TIMEZONE_MODES),
  language: z.enum(SUPPORTED_LOCALES),
  languageMode: z.enum(LANGUAGE_MODES),
});

export type LocalizationFormValues = z.infer<typeof localizationFormSchema>;
