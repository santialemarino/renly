import { z } from 'zod';

import {
  SPLIT_FIGURE_DECIMALS,
  SPLIT_PERCENTAGE_TOTAL,
  type SplitMethod,
} from '@/lib/constants/shared-expenses';

/*
 * The participant rows both shared-flow forms bind, and the three totals their editor checks.
 *
 * Extracted from the shared-expense schema when income arrived, for the reason `split-rules.ts` was:
 * the rules are about the SPLIT and not about either flow. Every comparison happens in integer
 * hundredths, which is the part worth not re-deriving.
 */

// A decimal string with at most `SPLIT_FIGURE_DECIMALS` places — the shape the running totals below
// can sum. Anything else contributes nothing rather than NaN.
const FIGURE_PATTERN = new RegExp(`^\\d+(\\.\\d{1,${SPLIT_FIGURE_DECIMALS}})?$`);

// One participant row. `included` is the checkbox; `figure` is whatever the chosen method needs and
// is ignored entirely by `equal`.
export const splitRowSchema = z.object({
  memberId: z.number(),
  included: z.boolean(),
  figure: z.string(),
});

export type SplitFormRow = z.infer<typeof splitRowSchema>;

/*
 * A decimal string as whole hundredths.
 *
 * Every total below is compared in integer hundredths rather than as floats, because
 * 33.33 + 33.33 + 33.34 does not equal 100 in binary — a form that looks correct and is then refused
 * by the API for a rounding the user cannot see. A blank or not-yet-valid field contributes 0.
 */
function figureHundredths(value: string): number {
  return FIGURE_PATTERN.test(value) ? Math.round(Number(value) * 100) : 0;
}

// The running total of the included participants' figures, in whole hundredths. Internal, like the
// conversion above: `splitFiguresTotal` is what the editor renders and what every comparison here
// funnels through, so a second public entry point would be a second way to sum the same rows.
function splitFiguresHundredths(splits: SplitFormRow[]): number {
  return splits.reduce(
    (total, split) => (split.included ? total + figureHundredths(split.figure) : total),
    0,
  );
}

// The same total as a number the caller can format — hundredths divided by 100, which is exact for
// every figure a money field can hold. Display only; every comparison stays in hundredths.
export function splitFiguresTotal(splits: SplitFormRow[]): number {
  return splitFiguresHundredths(splits) / 100;
}

// How many participants are checked. The API refuses zero (400 shared_split_no_participants), and so
// does this — the message belongs beside the list, where the checkboxes are.
export function includedSplitCount(splits: SplitFormRow[]): number {
  return splits.filter((split) => split.included).length;
}

/*
 * Whether the chosen method's figures satisfy its own rule. One function rather than three refines
 * so the editor can ask the same question the schema asks, and light the running total accordingly.
 *
 *   * `equal` divides by head count and has no figures to check.
 *   * `exact` amounts must already sum to the row's amount — never rescaled, so a mismatch is a
 *     refusal rather than something silently absorbed.
 *   * `percentage` figures must total exactly 100, for the same reason a pot's opening shares must:
 *     quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it.
 *   * `shares` are relative weights with no target, so the only thing that can be wrong is having
 *     nothing to divide by.
 */
export function splitFiguresBalance(
  method: SplitMethod,
  splits: SplitFormRow[],
  amount: string,
): boolean {
  if (method === 'equal') return true;
  const stated = splitFiguresHundredths(splits);
  if (method === 'shares') return stated > 0;
  if (method === 'percentage') return stated === SPLIT_PERCENTAGE_TOTAL * 100;
  return stated === figureHundredths(amount);
}
