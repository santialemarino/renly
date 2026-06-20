import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { EMAIL_REGEX } from '@/lib/constants/form';

export const forgotPasswordFormSchema = (t: ReturnType<typeof useTranslations>) =>
  z.object({
    email: z
      .string()
      .min(1, { message: t('form.errors.required') })
      .regex(EMAIL_REGEX, { message: t('form.errors.invalidEmail') }),
  });

export type ForgotPasswordFormData = z.infer<ReturnType<typeof forgotPasswordFormSchema>>;
