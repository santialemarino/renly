import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { EMAIL_REGEX, PASSWORD_MAX_LENGTH } from '@/lib/constants/form';

export const loginFormSchema = (t: ReturnType<typeof useTranslations>) =>
  z.object({
    email: z
      .string()
      .min(1, { message: t('form.errors.required') })
      .regex(EMAIL_REGEX, { message: t('form.errors.invalidEmail') }),
    password: z
      .string()
      .min(1, { message: t('form.errors.required') })
      .max(PASSWORD_MAX_LENGTH, {
        message: t('form.errors.passwordMaxLength', { length: PASSWORD_MAX_LENGTH }),
      }),
  });

export type LoginFormData = z.infer<ReturnType<typeof loginFormSchema>>;
