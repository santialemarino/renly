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

// The API's limit on a name (`users.name` is VARCHAR(255)).
export const NAME_MAX_LENGTH = 255;

export const changeNameSchema = (t: ReturnType<typeof useTranslations>, tooLongMsg: string) =>
  z.object({
    name: z
      .string()
      .trim()
      .min(1, { message: t('form.errors.required') })
      .max(NAME_MAX_LENGTH, { message: tooLongMsg }),
  });

export type ChangeNameData = z.infer<ReturnType<typeof changeNameSchema>>;
