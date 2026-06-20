import { useTranslations } from 'next-intl';
import { z } from 'zod';

import {
  EMAIL_REGEX,
  PASSWORD_CONTAINS_LOWERCASE_REGEX,
  PASSWORD_CONTAINS_NUMBER_REGEX,
  PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX,
  PASSWORD_CONTAINS_UPPERCASE_REGEX,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
} from '@/lib/constants/form';

export const changePasswordSchema = (t: ReturnType<typeof useTranslations>) =>
  z
    .object({
      currentPassword: z.string().min(1, { message: t('form.errors.required') }),
      newPassword: z
        .string()
        .min(PASSWORD_MIN_LENGTH, {
          message: t('form.errors.passwordMinLength', { length: PASSWORD_MIN_LENGTH }),
        })
        .max(PASSWORD_MAX_LENGTH, {
          message: t('form.errors.passwordMaxLength', { length: PASSWORD_MAX_LENGTH }),
        })
        .regex(PASSWORD_CONTAINS_UPPERCASE_REGEX, {
          message: t('form.errors.passwordRequirements'),
        })
        .regex(PASSWORD_CONTAINS_LOWERCASE_REGEX, {
          message: t('form.errors.passwordRequirements'),
        })
        .regex(PASSWORD_CONTAINS_NUMBER_REGEX, { message: t('form.errors.passwordRequirements') })
        .regex(PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX, {
          message: t('form.errors.passwordRequirements'),
        }),
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
