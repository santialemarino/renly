import { z } from 'zod';

import { TIMEZONE_MODES } from '@/lib/constants/timezones';

export const localizationFormSchema = z.object({
  timezone: z.string().min(1),
  timezoneMode: z.enum(TIMEZONE_MODES),
});

export type LocalizationFormValues = z.infer<typeof localizationFormSchema>;
