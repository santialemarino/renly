import { z } from 'zod';

import { GROUP_NAME_MAX } from '@/lib/constants/api-constants';
import {
  POT_MOVEMENT_TYPES,
  POT_PERCENTAGE_DECIMALS,
  POT_PERCENTAGE_TOTAL,
  POT_VISIBILITIES,
} from '@/lib/constants/pots';

/*
 * The pot forms' schemas. They validate what the API answers with a **422** — a malformed body, which
 * `REFUSAL_STATUSES` deliberately excludes, so it reaches the user as a generic message with no field
 * attached — plus the two domain rules whose refusal is far more useful beside the field than after a
 * submit (an opening's total, and a re-agreement naming one member twice).
 *
 * Everything the API answers with a 400/409 is left to the API and surfaced through the dialog's
 * conflict path, because a second copy of a domain rule is a second thing that can disagree with it.
 * The amount inputs already constrain their own shape (digits plus one separator, two decimals), so
 * these check magnitude rather than format.
 */

// A decimal string with at most `decimals` places, for the running-total sum below.
const PERCENTAGE_PATTERN = new RegExp(`^\\d+(\\.\\d{1,${POT_PERCENTAGE_DECIMALS}})?$`);

// A money or percentage figure the API requires to be > 0 (its Decimal fields carry `gt=0`, so a zero
// or a blank arrives as a 422 the user cannot act on).
function positiveField(requiredMsg: string, positiveMsg: string) {
  return z
    .string()
    .min(1, { message: requiredMsg })
    .refine((v) => Number(v) > 0, { message: positiveMsg });
}

export function buildPotFormSchema(requiredMsg: string) {
  return z.object({
    // Optional on purpose: a group's first pot needs no name (A4), and the UI labels it until there is
    // a second one to tell apart.
    name: z.string().max(GROUP_NAME_MAX).optional(),
    baseCurrency: z.string().min(1, { message: requiredMsg }),
    visibility: z.enum(POT_VISIBILITIES, { message: requiredMsg }),
  });
}

export type PotFormValues = z.infer<ReturnType<typeof buildPotFormSchema>>;

interface BuildPotOpeningFormSchemaArgs {
  requiredMsg: string;
  positiveMsg: string;
  totalMsg: string;
}

/*
 * The opening baseline: what the pot was worth on a date, and each owner's percentage of it.
 *
 * The shares array is seeded from the group's roster when the dialog opens, so every seat has a row and
 * a blank one means "owns none" rather than a missing key. The total is checked HERE as well as by the
 * API (400 pot_percentages_must_total_100) — the one domain rule worth duplicating, because the
 * percentages ARE the agreement and are never rescaled: someone a point out needs to see it beside the
 * running total, not after a submit.
 */
export function buildPotOpeningFormSchema({
  requiredMsg,
  positiveMsg,
  totalMsg,
}: BuildPotOpeningFormSchemaArgs) {
  return z
    .object({
      date: z.string().min(1, { message: requiredMsg }),
      value: positiveField(requiredMsg, positiveMsg),
      shares: z.array(z.object({ memberId: z.number(), percentage: z.string() })),
      notes: z.string().optional(),
    })
    .refine((values) => openingSharesTotal(values.shares) === POT_PERCENTAGE_TOTAL, {
      message: totalMsg,
      path: ['shares'],
    });
}

/*
 * The running total of an opening's percentages, in whole hundredths so the comparison against 100 is
 * integer arithmetic. Summing the decimal strings as floats makes 33.33 + 33.33 + 33.34 fail to equal
 * 100 — a form that looks correct and is then refused by the API for the rounding the user cannot see.
 * A field that is blank or not yet a valid decimal contributes nothing rather than NaN.
 */
export function openingSharesTotal(shares: { percentage: string }[]): number {
  const hundredths = shares.reduce((total, share) => {
    if (!PERCENTAGE_PATTERN.test(share.percentage)) return total;
    return total + Math.round(Number(share.percentage) * 100);
  }, 0);
  return hundredths / 100;
}

export type PotOpeningFormValues = z.infer<ReturnType<typeof buildPotOpeningFormSchema>>;

interface BuildPotMovementFormSchemaArgs {
  baseCurrency: string;
  requiredMsg: string;
  positiveMsg: string;
}

/*
 * A contribution or a withdrawal.
 *
 * `amount` is always in the PRIVATE side's currency and `baseAmount` always in the pot's — different
 * columns server-side, and which one moves which balance depends on the direction. So `baseAmount` is
 * required exactly when the two currencies differ, matching the API (400 pot_base_amount_required):
 * deriving it would mean storing a rate, which the money model forbids. Checked here rather than left
 * to the API because the dialog knows the pot's base currency, which is the whole comparison — unlike
 * the transfer form, whose rule needs two accounts its schema cannot see.
 */
export function buildPotMovementFormSchema({
  baseCurrency,
  requiredMsg,
  positiveMsg,
}: BuildPotMovementFormSchemaArgs) {
  return z
    .object({
      type: z.enum(POT_MOVEMENT_TYPES, { message: requiredMsg }),
      date: z.string().min(1, { message: requiredMsg }),
      memberId: z.string().min(1, { message: requiredMsg }),
      amount: positiveField(requiredMsg, positiveMsg),
      amountCurrency: z.string().min(1, { message: requiredMsg }),
      baseAmount: z.string().optional(),
      // Both legs optional: money can arrive from outside Renly, or land in an investment rather than a
      // tracked account.
      privateAccountId: z.string().optional(),
      potAccountId: z.string().optional(),
      notes: z.string().optional(),
    })
    .refine(
      (values) =>
        values.amountCurrency === baseCurrency ||
        (!!values.baseAmount && Number(values.baseAmount) > 0),
      { message: requiredMsg, path: ['baseAmount'] },
    );
}

export type PotMovementFormValues = z.infer<ReturnType<typeof buildPotMovementFormSchema>>;

interface BuildPotReagreementFormSchemaArgs {
  requiredMsg: string;
  positiveMsg: string;
  rangeMsg: string;
  sameMemberMsg: string;
}

/*
 * A re-agreement: units moving between two members with no money at all. Taken as a percentage of the
 * whole pot, because percentages go in and percentages come out (U2) — a unit count appears nowhere.
 *
 * The upper bound is checked here because the API's refusal for it is `pot_insufficient_units`, which
 * describes what the maths hit rather than what the user did: "more than that member holds" reads as a
 * fact about the other person when they typed 150.
 */
export function buildPotReagreementFormSchema({
  requiredMsg,
  positiveMsg,
  rangeMsg,
  sameMemberMsg,
}: BuildPotReagreementFormSchemaArgs) {
  return z
    .object({
      date: z.string().min(1, { message: requiredMsg }),
      fromMemberId: z.string().min(1, { message: requiredMsg }),
      toMemberId: z.string().min(1, { message: requiredMsg }),
      percentage: positiveField(requiredMsg, positiveMsg).refine(
        (v) => Number(v) <= POT_PERCENTAGE_TOTAL,
        { message: rangeMsg },
      ),
      notes: z.string().optional(),
    })
    .refine((values) => values.fromMemberId !== values.toMemberId, {
      message: sameMemberMsg,
      path: ['toMemberId'],
    });
}

export type PotReagreementFormValues = z.infer<ReturnType<typeof buildPotReagreementFormSchema>>;

/*
 * The per-member access row an admin sets. `canWrite` forces `canView` server-side (a CHECK on the
 * table as well), so the form sends the pair as chosen and lets the API resolve the implication rather
 * than the UI second-guessing it.
 */
export function buildPotPermissionFormSchema() {
  return z.object({ canView: z.boolean(), canWrite: z.boolean() });
}

export type PotPermissionFormValues = z.infer<ReturnType<typeof buildPotPermissionFormSchema>>;
