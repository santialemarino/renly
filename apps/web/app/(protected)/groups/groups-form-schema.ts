import { z } from 'zod';

import { GROUP_NAME_MAX } from '@/lib/constants/db-constraints';

export function buildGroupFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, requiredMsg).max(GROUP_NAME_MAX),
    investmentIds: z.array(z.number()).optional(),
  });
}

export type GroupFormValues = z.infer<ReturnType<typeof buildGroupFormSchema>>;
