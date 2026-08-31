/*
 * The shared-expense enums and the two magnitudes its split editor checks, mirroring the API's
 * `split_method`. They live here rather than beside the shared-expense fetcher for the same reason
 * GROUP_KINDS and POT_CADENCES do: every consumer is a client component and `lib/api/*` is
 * server-only, so importing a runtime value from there breaks the build.
 *
 * The array is exhaustive and in display order, so adding a method to the API without adding its
 * translation is a type error at the picker rather than a missing label at runtime.
 */

/*
 * How one bill is divided. Ordered easiest-first, which is also how often each is used: `equal` is
 * the default and needs no figures at all, then the three that do — an amount each, a weight each, a
 * percentage each.
 *
 * What the per-participant `figure` means changes with the method and nothing else does, which is
 * why the API takes one field rather than three: it is ignored by `equal`, an amount for `exact`, a
 * weight for `shares`, and a percentage for `percentage`.
 */
export const SPLIT_METHODS = ['equal', 'exact', 'shares', 'percentage'] as const;

export type SplitMethod = (typeof SPLIT_METHODS)[number];

/*
 * The default a group starts on, mirroring the API's own column default. Named here so a form that
 * cannot read the group's money settings (a fetch that failed, or a brand-new group) still opens on
 * the same method the backend would have chosen.
 */
export const DEFAULT_SPLIT_METHOD: SplitMethod = 'equal';

/*
 * The two methods that carry a total the editor can check before submitting: `exact` must add up to
 * the expense's amount and `percentage` to 100. `shares` are relative weights with no target, and
 * `equal` takes no figures at all — so neither has a running total to show.
 */
export const SPLIT_METHODS_WITH_TOTAL: SplitMethod[] = ['exact', 'percentage'];

/*
 * The percentage a `percentage` split must reach — never rescaled, exactly as a pot's opening shares
 * are not, because quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it. Two decimals
 * because that is the precision the API's Decimal fields accept, and the precision at which a
 * three-way split still visibly sums to 100.
 */
export const SPLIT_PERCENTAGE_TOTAL = 100;

export const SPLIT_FIGURE_DECIMALS = 2;
