/*
 * The shared-income enum, mirroring the API's `income_destination`. It lives here rather than beside
 * the shared-income fetcher for the same reason SPLIT_METHODS does: every consumer is a client
 * component and `lib/api/*` is server-only, so importing a runtime value from there breaks the build.
 *
 * The split methods are NOT duplicated here — income divides by exactly the same four, and the group's
 * agreed default applies to both flows, so both read `lib/constants/shared-expenses`.
 */

/*
 * Where money the group shares ends up (F2).
 *
 *   * `joint` — it lands in a shared account a pot holds, so the pot is worth more and EVERY owner's
 *     share rises in proportion. Nobody's percentage moves: pro-rata growth needs no ownership event.
 *   * `distributed` — it reaches one person, and becomes each owner's own money in their proportions.
 *     Whoever collected it holds the rest as a balance until they pass it on.
 *
 * Ordered joint-first because that is the answer for money the household keeps together, which is the
 * case F1's default split is built around.
 */
export const INCOME_DESTINATIONS = ['joint', 'distributed'] as const;

export type IncomeDestination = (typeof INCOME_DESTINATIONS)[number];

/*
 * What the form opens on when nothing else decides it — no remembered choice for this source, and no
 * shared account in the currency to land in. `distributed` rather than `joint` because it is the one
 * that is always recordable: joint money has to land in a shared account the group may not have yet,
 * whereas somebody collecting the money is true of every household that has just been handed cash.
 */
export const DEFAULT_INCOME_DESTINATION: IncomeDestination = 'distributed';
