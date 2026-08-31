import { z } from 'zod';

import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { EXPENSE_CATEGORIES, PAYMENT_METHODS } from '@/lib/constants/categories';
import {
  SPLIT_FIGURE_DECIMALS,
  SPLIT_METHODS,
  SPLIT_PERCENTAGE_TOTAL,
  type SplitMethod,
} from '@/lib/constants/shared-expenses';

/*
 * The shared-expense form's schema.
 *
 * It validates what the API answers with a **422** — a malformed body, which `REFUSAL_STATUSES`
 * deliberately excludes, so it would reach the user as a generic message with no field attached —
 * plus the three split rules whose refusal is far more useful beside the running total than after a
 * submit: exact amounts that do not add up, percentages that do not reach 100, and shares that are
 * all zero.
 *
 * Everything the API answers with a 400/404 is left to the API and surfaced through the dialog's
 * conflict path, because a second copy of a domain rule is a second thing that can disagree with it.
 * The one exception is documented at `inactiveSeatNames` in `shared-expense-rules.ts`, whose refusal
 * carries no error code and so cannot be localized.
 */

// A decimal string with at most `SPLIT_FIGURE_DECIMALS` places — the shape the running totals below
// can sum. Anything else contributes nothing rather than NaN.
const FIGURE_PATTERN = new RegExp(`^\\d+(\\.\\d{1,${SPLIT_FIGURE_DECIMALS}})?$`);

/*
 * How the funding half of the form is answered — a control of this form's own rather than an API
 * enum, which is why it stays here and unexported: `joint` means a shared account fronted it, in
 * which case the API forbids naming a payer at all, and `member` means one person did and must be
 * named. The API has no such field; it reads the two apart from what the request names.
 */
const FUNDING_SOURCES = ['member', 'joint'] as const;

// One participant row. `included` is the checkbox; `figure` is whatever the chosen method needs and
// is ignored entirely by `equal`.
const splitRowSchema = z.object({
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

// How many participants are checked. The API refuses zero (400 shared_expense_no_participants), and
// so does this — the message belongs beside the list, where the checkboxes are.
export function includedSplitCount(splits: SplitFormRow[]): number {
  return splits.filter((split) => split.included).length;
}

/*
 * Whether the chosen method's figures satisfy its own rule. One function rather than three refines
 * so the editor can ask the same question the schema asks, and light the running total accordingly.
 *
 *   * `equal` divides by head count and has no figures to check.
 *   * `exact` amounts must already sum to the expense's amount — never rescaled, so a mismatch is a
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

interface BuildSharedExpenseFormSchemaArgs {
  requiredMsg: string;
  positiveMsg: string;
  participantsMsg: string;
  splitTotalMsg: string;
}

/*
 * The form behind both recording and replacing a shared expense — one schema, because the API's PUT
 * is a full replacement rather than a patch: the amount, the method and the participants are one
 * interlocking statement, so an edit restates all of it.
 *
 * The two funding branches are checked here rather than left to the API because each is a required
 * field the form knows is required: a shared account when joint money paid, a payer when somebody
 * did. Both would otherwise arrive as a 400 with no field to attach the message to.
 */
export function buildSharedExpenseFormSchema({
  requiredMsg,
  positiveMsg,
  participantsMsg,
  splitTotalMsg,
}: BuildSharedExpenseFormSchemaArgs) {
  return z
    .object({
      date: z.string().min(1, { message: requiredMsg }),
      amount: z
        .string()
        .min(1, { message: requiredMsg })
        .refine((v) => Number(v) > 0, { message: positiveMsg }),
      currency: z.string().min(1, { message: requiredMsg }),
      category: z.enum(EXPENSE_CATEGORIES).optional(),
      notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
      splitMethod: z.enum(SPLIT_METHODS, { message: requiredMsg }),
      splits: z.array(splitRowSchema),
      fundingSource: z.enum(FUNDING_SOURCES, { message: requiredMsg }),
      /*
       * Both OPTIONAL, and that is load-bearing rather than lax — each is required on exactly one
       * funding branch, and the superRefine below is what enforces that.
       *
       * They have to be optional because react-hook-form UNREGISTERS a field when its control leaves
       * the DOM, and unregistering DELETES the value: switching the funding source unmounts one of
       * these two, so by the time the form is submitted that key is gone entirely. A required
       * `z.string()` then fails with "expected string, received undefined" — on a field that is no
       * longer on screen, so there is no FormMessage to render it and no `aria-invalid` to see. The
       * submit does nothing at all, with no error anywhere and every static check green. Only the
       * browser found it, and only after instrumenting react-hook-form's own invalid callback.
       */
      payerMemberId: z.string().optional(),
      sharedAccountId: z.string().optional(),
      paymentMethod: z.enum(PAYMENT_METHODS).optional(),
      creditCardId: z.number().optional(),
      accountId: z.number().nullable().optional(),
    })
    .superRefine((values, ctx) => {
      if (values.fundingSource === 'joint' && !values.sharedAccountId) {
        ctx.addIssue({ code: 'custom', message: requiredMsg, path: ['sharedAccountId'] });
      }
      if (values.fundingSource === 'member' && !values.payerMemberId) {
        ctx.addIssue({ code: 'custom', message: requiredMsg, path: ['payerMemberId'] });
      }
      /*
       * Both of these land on the `splits` ARRAY, whose react-hook-form entry has no `message` a
       * FormMessage could render — so the editor states them in words beside the running total
       * instead, and asks `splitFiguresBalance` / `includedSplitCount` the same questions. The issues
       * are still raised because they are what stops the submit; without them an unbalanced form
       * would post and be refused by the API.
       */
      if (includedSplitCount(values.splits) === 0) {
        ctx.addIssue({ code: 'custom', message: participantsMsg, path: ['splits'] });
      }
      if (!splitFiguresBalance(values.splitMethod, values.splits, values.amount)) {
        ctx.addIssue({ code: 'custom', message: splitTotalMsg, path: ['splits'] });
      }
    });
}

export type SharedExpenseFormValues = z.infer<ReturnType<typeof buildSharedExpenseFormSchema>>;
