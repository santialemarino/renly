/*
 * Collection targets are allocation goals, each a share of the whole portfolio, so together they mean
 * something only while they fit in 100%. Going over is allowed — a target is a goal rather than a
 * fact, and a user part-way through rebalancing their goals will pass through such a state — so this
 * only ever WARNS: on save, and on the collections page while it holds.
 *
 * An investment can be in more than one collection, so the targets are not a partition of the
 * holdings; what they sum is the user's stated goals, which is exactly what the warning is about.
 */

// The most the targets can add up to before the warning shows.
export const COLLECTION_TARGETS_MAX_PCT = 100;

// Two decimals is the precision a target is entered and stored with; summing floats can land a hair
// over an exact 100 (33.33 + 33.33 + 33.34), which must not warn.
const PCT_EPSILON = 0.005;

// The sum of every collection's target, skipping those without one and, when given, the one being
// edited — whose new value the form adds itself.
export function sumCollectionTargets(
  collections: { id: number; targetPercentage: number | null }[],
  excludeId?: number,
): number {
  return collections.reduce(
    (total, collection) =>
      collection.id === excludeId ? total : total + (collection.targetPercentage ?? 0),
    0,
  );
}

// Whether a targets total is over 100%.
export function targetsExceedMax(total: number): boolean {
  return total > COLLECTION_TARGETS_MAX_PCT + PCT_EPSILON;
}
