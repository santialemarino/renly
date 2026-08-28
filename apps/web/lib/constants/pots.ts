/*
 * The pot enums, mirroring the API's `pot_visibility` and `ownership_event_type`. They live here
 * rather than beside the pots fetcher for the same reason GROUP_KINDS does: every consumer is a
 * client component and `lib/api/*` is server-only, so importing a runtime value from there breaks
 * the build.
 *
 * Each array is exhaustive and in display order, so adding a value to the API without adding its
 * translation is a type error at the picker rather than a missing label at runtime.
 */

/*
 * Who can see a pot by default. It is only the DEFAULT — an explicit per-member permission row wins
 * in both directions, and `owners` fails closed: no row, no access.
 */
export const POT_VISIBILITIES = ['members', 'owners'] as const;

export type PotVisibility = (typeof POT_VISIBILITIES)[number];

/*
 * Every kind of entry the ownership ledger holds, in the order they can first occur. The opening is
 * the division every later percentage derives from; a re-agreement is the only one that moves no
 * money at all.
 */
export const OWNERSHIP_EVENT_TYPES = [
  'opening',
  'contribution',
  'withdrawal',
  'reagreement',
] as const;

export type OwnershipEventType = (typeof OWNERSHIP_EVENT_TYPES)[number];

/*
 * The two the movements endpoint accepts. An opening and a re-agreement take different inputs and
 * have endpoints of their own, which is exactly what `pot_unsupported_movement` refuses — so the
 * movement form builds its picker from this narrower list rather than filtering the full one.
 */
export const POT_MOVEMENT_TYPES = ['contribution', 'withdrawal'] as const;

export type PotMovementType = (typeof POT_MOVEMENT_TYPES)[number];

/*
 * The percentages an opening or a re-agreement is expressed in. NUMERIC(5,2) on the API's
 * re-agreement body, and the opening's shares must total exactly this — never rescaled, because
 * quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it.
 */
export const POT_PERCENTAGE_TOTAL = 100;

export const POT_PERCENTAGE_DECIMALS = 2;
