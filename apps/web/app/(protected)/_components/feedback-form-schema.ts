import { useTranslations } from 'next-intl';
import { z } from 'zod';

import { FEEDBACK_CATEGORIES, MAX_FEEDBACK_LENGTH } from '@/lib/constants/feedback';

export const feedbackFormSchema = (t: ReturnType<typeof useTranslations>) =>
  z.object({
    category: z.enum(FEEDBACK_CATEGORIES, { message: t('form.errors.required') }),
    message: z
      .string()
      .trim()
      .min(1, { message: t('form.errors.required') })
      .max(MAX_FEEDBACK_LENGTH, {
        message: t('form.errors.tooLong', { max: MAX_FEEDBACK_LENGTH }),
      }),
  });

export type FeedbackFormData = z.infer<ReturnType<typeof feedbackFormSchema>>;
