import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { EMAIL_REGEX } from '@/lib/constants/form';
import { newPasswordSchema } from '@/lib/new-password';

export const changePasswordSchema = (t: ReturnType<typeof useTranslations>) =>
  z
    .object({
      currentPassword: z.string().min(1, { message: t('form.errors.required') }),
      newPassword: newPasswordSchema(t),
      confirmPassword: z.string().min(1, { message: t('form.errors.required') }),
    })
    .refine((data) => data.newPassword === data.confirmPassword, {
      message: t('form.errors.passwordMismatch'),
      path: ['confirmPassword'],
    });

export type ChangePasswordData = z.infer<ReturnType<typeof changePasswordSchema>>;

export const changeEmailSchema = (t: ReturnType<typeof useTranslations>) =>
  z.object({
    currentPassword: z.string().min(1, { message: t('form.errors.required') }),
    newEmail: z
      .string()
      .min(1, { message: t('form.errors.required') })
      .regex(EMAIL_REGEX, { message: t('form.errors.invalidEmail') }),
  });

export type ChangeEmailData = z.infer<ReturnType<typeof changeEmailSchema>>;
