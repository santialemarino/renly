/*
 * The group enums, mirroring the API's `group_kind` and `group_member_role`. They live here rather
 * than beside the groups fetcher because the group form and the roster are client components and
 * `lib/api/*` is server-only — importing a runtime value from there breaks the build (the same reason
 * ACCOUNT_TYPES and MOVEMENT_KINDS sit in `constants/accounts.ts`).
 *
 * Both arrays are exhaustive and in display order, so adding a kind to the API without adding its
 * `shared.kinds.*` translation is a type error at the picker rather than a missing label at runtime.
 */
export const GROUP_KINDS = ['household', 'couple', 'trip', 'flat', 'other'] as const;

export type GroupKind = (typeof GROUP_KINDS)[number];

/*
 * Group administration only. An admin manages members, settings and invites and gains no additional
 * visibility into anyone's data — nothing in the app gates a READ on this.
 */
export const GROUP_ROLES = ['admin', 'member'] as const;

export type GroupRole = (typeof GROUP_ROLES)[number];
