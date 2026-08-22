import { z } from 'zod';

import { GROUP_NAME_MAX } from '@/lib/constants/api-constants';
import { EMAIL_REGEX } from '@/lib/constants/form';
import { GROUP_KINDS, GROUP_ROLES } from '@/lib/constants/groups';

export function buildGroupFormSchema(requiredMsg: string) {
  return z.object({
    name: z.string().min(1, requiredMsg).max(GROUP_NAME_MAX),
    kind: z.enum(GROUP_KINDS, { message: requiredMsg }),
    // How the creator is shown in the group; blank falls back to their account name server-side.
    displayName: z.string().max(GROUP_NAME_MAX).optional(),
  });
}

export type GroupFormValues = z.infer<ReturnType<typeof buildGroupFormSchema>>;

export function buildGroupMemberFormSchema(requiredMsg: string) {
  return z.object({
    displayName: z.string().min(1, requiredMsg).max(GROUP_NAME_MAX),
    role: z.enum(GROUP_ROLES, { message: requiredMsg }),
  });
}

export type GroupMemberFormValues = z.infer<ReturnType<typeof buildGroupMemberFormSchema>>;

/*
 * The invite form's email is OPTIONAL: leaving it blank is the shareable-link half of the feature
 * (nothing is sent, the caller shares the returned URL). It is validated only when present, and
 * reuses the shared EMAIL_REGEX so a group invite rejects the same addresses every other form does.
 */
export function buildGroupInviteFormSchema(invalidEmailMsg: string) {
  return z.object({
    email: z
      .string()
      .optional()
      .refine((v) => !v || EMAIL_REGEX.test(v), { message: invalidEmailMsg }),
  });
}

export type GroupInviteFormValues = z.infer<ReturnType<typeof buildGroupInviteFormSchema>>;
