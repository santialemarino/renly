import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { EMAIL_REGEX } from '@/lib/constants/form';

export const inviteFormSchema = (t: ReturnType<typeof useTranslations>) =>
  z.object({
    email: z
      .string()
      .min(1, { message: t('form.errors.required') })
      .regex(EMAIL_REGEX, { message: t('form.errors.invalidEmail') }),
  });

export type InviteFormData = z.infer<ReturnType<typeof inviteFormSchema>>;
