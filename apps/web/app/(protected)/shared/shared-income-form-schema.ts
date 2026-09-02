import { z } from 'zod';

import {
  includedSplitCount,
  splitFiguresBalance,
  splitRowSchema,
} from '@/app/(protected)/shared/split-form-schema';
import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { INCOME_CATEGORIES } from '@/lib/constants/categories';
import { SPLIT_METHODS } from '@/lib/constants/shared-expenses';
import { INCOME_DESTINATIONS } from '@/lib/constants/shared-income';

/*
 * The shared-income form's schema — the mirror of the shared-expense one.
 *
 * It validates what the API answers with a **422** — a malformed body, which `REFUSAL_STATUSES`
 * deliberately excludes, so it would reach the user as a generic message with no field attached —
 * plus the three split rules whose refusal is far more useful beside the running total than after a
 * submit: exact amounts that do not add up, percentages that do not reach 100, and shares that are
 * all zero.
 *
 * Everything the API answers with a 400/404 is left to the API and surfaced through the dialog's
 * conflict path, because a second copy of a domain rule is a second thing that can disagree with it.
 * The one exception is documented at `inactiveSeatNames` in `shared-income-rules.ts`, whose refusal
 * carries no error code and so cannot be localized.
 *
 * The split helpers come from `split-form-schema` rather than being restated: income divides by the
 * same four methods and the totals are compared in the same integer hundredths.
 */

// Reuses the notes cap the expense forms use — the API's max_length is 500 on every notes field, so
// one constant is the honest reading rather than an expense-shaped one applied to income.
interface BuildSharedIncomeFormSchemaArgs {
  requiredMsg: string;
  positiveMsg: string;
  participantsMsg: string;
  splitTotalMsg: string;
}

/*
 * The form behind both recording and replacing shared income — one schema, because the API's PUT is a
 * full replacement rather than a patch: the amount, the method and the participants are one
 * interlocking statement, so an edit restates all of it.
 *
 * The two destination branches are checked here rather than left to the API because each is a
 * required field the form knows is required: a shared account when the money stayed joint, a recipient
 * when it reached one person. Both would otherwise arrive as a 400 with no field to attach the
 * message to.
 */
export function buildSharedIncomeFormSchema({
  requiredMsg,
  positiveMsg,
  participantsMsg,
  splitTotalMsg,
}: BuildSharedIncomeFormSchemaArgs) {
  return z
    .object({
      date: z.string().min(1, { message: requiredMsg }),
      amount: z
        .string()
        .min(1, { message: requiredMsg })
        .refine((v) => Number(v) > 0, { message: positiveMsg }),
      currency: z.string().min(1, { message: requiredMsg }),
      category: z.enum(INCOME_CATEGORIES).optional(),
      notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
      splitMethod: z.enum(SPLIT_METHODS, { message: requiredMsg }),
      splits: z.array(splitRowSchema),
      destination: z.enum(INCOME_DESTINATIONS, { message: requiredMsg }),
      /*
       * The source asset, as a STRING because that is what a combobox binds. Its own sentinel for
       * "nothing in particular" rather than an empty value, so the field always has a selection and
       * the picker never renders a placeholder for a choice the user actually made.
       */
      sourceInvestmentId: z.string(),
      /*
       * Both OPTIONAL, and that is load-bearing rather than lax — each is required on exactly one
       * destination branch, and the superRefine below is what enforces that.
       *
       * They have to be optional because react-hook-form UNREGISTERS a field when its control leaves
       * the DOM, and unregistering DELETES the value: switching the destination unmounts one of these
       * two, so by the time the form is submitted that key is gone entirely. A required `z.string()`
       * then fails with "expected string, received undefined" — on a field that is no longer on
       * screen, so there is no FormMessage to render it and no `aria-invalid` to see. The submit does
       * nothing at all, with no error anywhere and every static check green. That is exactly the
       * defect the expense form shipped and had to instrument react-hook-form to find; this schema is
       * written the fixed way from the start.
       */
      receivedByMemberId: z.string().optional(),
      sharedAccountId: z.string().optional(),
      accountId: z.number().nullable().optional(),
    })
    .superRefine((values, ctx) => {
      if (values.destination === 'joint' && !values.sharedAccountId) {
        ctx.addIssue({ code: 'custom', message: requiredMsg, path: ['sharedAccountId'] });
      }
      if (values.destination === 'distributed' && !values.receivedByMemberId) {
        ctx.addIssue({ code: 'custom', message: requiredMsg, path: ['receivedByMemberId'] });
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

export type SharedIncomeFormValues = z.infer<ReturnType<typeof buildSharedIncomeFormSchema>>;

/*
 * The picker value for "nothing in particular" — income the group shares that came from no asset it
 * co-owns, which is every case F1's inheritance has nothing to say about. A sentinel rather than an
 * empty string for the reason `NONE_ACCOUNT` is one in `AccountField`: a combobox cannot bind cleanly
 * to a nullish value, and an empty selection renders as the placeholder, which reads as unanswered.
 */
export const NO_SOURCE = 'none';
