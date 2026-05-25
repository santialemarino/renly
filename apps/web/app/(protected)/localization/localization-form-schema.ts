import { z } from 'zod';

import { SUPPORTED_LOCALES } from '@/config/constants';
import { LANGUAGE_MODES } from '@/lib/constants/languages';
import { TIMEZONE_MODES } from '@/lib/constants/timezones';

export const localizationFormSchema = z.object({
  timezone: z.string().min(1),
  timezoneMode: z.enum(TIMEZONE_MODES),
  language: z.enum(SUPPORTED_LOCALES),
  languageMode: z.enum(LANGUAGE_MODES),
});

export type LocalizationFormValues = z.infer<typeof localizationFormSchema>;
