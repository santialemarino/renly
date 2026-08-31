/*
 * The settlement enum, mirroring the API's `group_settlement_status`. Here rather than beside the
 * settlements fetcher for the same reason GROUP_KINDS is: every consumer is a client component and
 * `lib/api/*` is server-only, so importing a runtime value from there breaks the build.
 *
 * Exhaustive and in lifecycle order, so adding a status to the API without adding its translation is
 * a type error rather than a missing badge label at runtime.
 *
 * `written_off` is a status rather than a separate table because a write-off clears the same bucket a
 * payment does and the arithmetic is identical — the creditor gives up the claim, which lowers their
 * position and raises the debtor's. What differs is only that no money moved, which is why it can
 * carry no cash leg and why only the creditor may record or remove one.
 */
export const SETTLEMENT_STATUSES = ['pending', 'confirmed', 'written_off'] as const;

export type SettlementStatus = (typeof SETTLEMENT_STATUSES)[number];
