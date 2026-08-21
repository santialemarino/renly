import { z } from 'zod';

import { COLLECTION_NAME_MAX } from '@/lib/constants/api-constants';

export function buildCollectionFormSchema(requiredMsg: string, invalidTargetMsg: string) {
  return z.object({
    name: z.string().min(1, requiredMsg).max(COLLECTION_NAME_MAX),
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

export type CollectionFormValues = z.infer<ReturnType<typeof buildCollectionFormSchema>>;
