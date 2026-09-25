import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { USER_NAME_MAX } from '@/lib/constants/api-constants';
import { EMAIL_REGEX } from '@/lib/constants/form';
import { newPasswordSchema } from '@/lib/new-password';

export const signupFormSchema = (t: ReturnType<typeof useTranslations>) =>
  z
    .object({
      name: z
        .string()
        .min(1, { message: t('form.errors.required') })
        .max(USER_NAME_MAX, { message: t('form.errors.tooLong', { max: USER_NAME_MAX }) }),
      email: z
        .string()
        .min(1, { message: t('form.errors.required') })
        .regex(EMAIL_REGEX, { message: t('form.errors.invalidEmail') }),
      password: newPasswordSchema(t),
      confirmPassword: z.string().min(1, { message: t('form.errors.required') }),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: t('form.errors.passwordMismatch'),
      path: ['confirmPassword'],
    });

export type SignupFormData = z.infer<ReturnType<typeof signupFormSchema>>;
