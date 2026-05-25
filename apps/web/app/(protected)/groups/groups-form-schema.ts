import { z } from 'zod';

import { GROUP_NAME_MAX } from '@/lib/constants/api-constants';

export function buildGroupFormSchema(requiredMsg: string, invalidTargetMsg: string) {
  return z.object({
    name: z.string().min(1, requiredMsg).max(GROUP_NAME_MAX),
    targetPercentage: z
      .string()
      .optional()
      .refine(
        (v) => {
          if (!v) return true;
          const n = Number(v);
          return Number.isFinite(n) && n >= 0 && n <= 100;
        },
        { message: invalidTargetMsg },
      ),
    investmentIds: z.array(z.number()).optional(),
  });
}

export type GroupFormValues = z.infer<ReturnType<typeof buildGroupFormSchema>>;
