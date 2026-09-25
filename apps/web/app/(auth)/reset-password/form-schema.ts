import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { newPasswordSchema } from '@/lib/new-password';

export const resetPasswordFormSchema = (t: ReturnType<typeof useTranslations>) =>
  z
    .object({
      password: newPasswordSchema(t),
      confirmPassword: z.string().min(1, { message: t('form.errors.required') }),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: t('form.errors.passwordMismatch'),
      path: ['confirmPassword'],
    });

export type ResetPasswordFormData = z.infer<ReturnType<typeof resetPasswordFormSchema>>;
