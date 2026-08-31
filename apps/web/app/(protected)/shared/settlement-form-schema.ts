import { z } from 'zod';

import { legCrossesCurrency } from '@/app/(protected)/shared/settlement-rules';
import { EXPENSE_NOTES_MAX } from '@/lib/constants/api-constants';
import { SPLIT_METHODS } from '@/lib/constants/shared-expenses';

/*
 * The schemas behind recording a payment, writing a balance off, attaching a cash leg, and the money
 * settings a group holds in common.
 *
 * Each validates what the API answers with a **422**, plus the two rules whose refusal is far more
 * useful beside the field: a settlement between one person and themselves, and a cross-currency leg
 * that does not say how much moved. Everything else — who may confirm, who may write off, whether a
 * date precedes an account's opening — is left to the API and surfaced through the conflict path,
 * because a second copy of a domain rule is a second thing that can disagree with it.
 */

// A money figure the API requires to be > 0 (its Decimal fields carry `gt=0`, so a zero or a blank
// arrives as a 422 the user cannot act on). Shared by all three money schemas below.
function positiveAmount(requiredMsg: string, positiveMsg: string) {
  return z
    .string()
    .min(1, { message: requiredMsg })
    .refine((v) => Number(v) > 0, { message: positiveMsg });
}

/*
 * Whether a cash leg has said what moved through it.
 *
 * Required exactly when the account's currency differs from the bucket's, mirroring
 * 400 group_settlement_leg_amount_required: the two are denominated differently and no rate is ever
 * stored, so the figure has to be stated. Within one currency the account moved what the bucket
 * cleared and the API refuses a different figure outright, so the field is not merely unnecessary
 * there — it is a way to be wrong.
 *
 * One predicate rather than a copy per schema, because both the settle form and the leg form ask it.
 */
function legAmountStated(
  values: { accountId?: string; legCurrency?: string; legAmount?: string },
  bucketCurrency: string,
): boolean {
  if (!values.accountId) return true;
  if (!legCrossesCurrency(values.legCurrency, bucketCurrency)) return true;
  return !!values.legAmount && Number(values.legAmount) > 0;
}

interface BuildSettlementFormSchemaArgs {
  bucketCurrency: string;
  requiredMsg: string;
  positiveMsg: string;
  sameMemberMsg: string;
}

/*
 * Recording one payment against one bucket.
 *
 * `amount` is editable and pre-filled with the suggested figure, which is D28's "one tap for the
 * common case" without forbidding the two that are not: a partial payment lowers the balance and
 * settlements stay additive until it clears, and an overpayment flips it the other way. Both are the
 * flip side of an editable field rather than states to block.
 *
 * The cash leg is the CALLER's own and nothing here can name the other party's — the form only ever
 * offers the caller's side, and the API refuses the other outright (400 group_settlement_foreign_leg)
 * because the row-level policies genuinely hide those accounts.
 */
export function buildSettlementFormSchema({
  bucketCurrency,
  requiredMsg,
  positiveMsg,
  sameMemberMsg,
}: BuildSettlementFormSchemaArgs) {
  return z
    .object({
      fromMemberId: z.string().min(1, { message: requiredMsg }),
      toMemberId: z.string().min(1, { message: requiredMsg }),
      date: z.string().min(1, { message: requiredMsg }),
      amount: positiveAmount(requiredMsg, positiveMsg),
      // The caller's own leg. Both optional: mark-as-paid with no account named is the v1 default,
      // and the only thing a name-only member's side can ever be.
      accountId: z.string().optional(),
      // Not a field the user fills — the account picker writes it, so the cross-currency rule below
      // can be asked without the schema knowing the account list.
      legCurrency: z.string().optional(),
      legAmount: z.string().optional(),
      notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
    })
    .refine((values) => values.fromMemberId !== values.toMemberId, {
      message: sameMemberMsg,
      path: ['toMemberId'],
    })
    .refine((values) => legAmountStated(values, bucketCurrency), {
      message: requiredMsg,
      path: ['legAmount'],
    });
}

export type SettlementFormValues = z.infer<ReturnType<typeof buildSettlementFormSchema>>;

interface BuildSettlementLegFormSchemaArgs {
  bucketCurrency: string;
  requiredMsg: string;
}

/*
 * Attaching (or clearing) the caller's own cash leg after the fact — usually the payee, at the moment
 * they confirm they received the money.
 *
 * It exists as its own form because the leg is the one part of a shared settlement row that only its
 * owner can state: a settlement is one record visible to both parties, but which of MY accounts it
 * moved through is a fact only I have, and only I can even see the account.
 */
export function buildSettlementLegFormSchema({
  bucketCurrency,
  requiredMsg,
}: BuildSettlementLegFormSchemaArgs) {
  return z
    .object({
      accountId: z.string().optional(),
      legCurrency: z.string().optional(),
      legAmount: z.string().optional(),
    })
    .refine((values) => legAmountStated(values, bucketCurrency), {
      message: requiredMsg,
      path: ['legAmount'],
    });
}

export type SettlementLegFormValues = z.infer<ReturnType<typeof buildSettlementLegFormSchema>>;

interface BuildWriteOffFormSchemaArgs {
  requiredMsg: string;
  positiveMsg: string;
}

/*
 * Giving up on a debt. It clears the same bucket a payment would and moves no money at all, so it
 * names no account and carries no leg — which is also why the API refuses one (409
 * group_settlement_write_off_has_no_leg).
 *
 * The amount stays editable: forgiving part of what someone owes is a real thing to do, and the API
 * takes any figure. The two seats are not editable and so are not fields — a write-off is always
 * recorded against one suggested payment, by the person it would have been paid to.
 */
export function buildWriteOffFormSchema({ requiredMsg, positiveMsg }: BuildWriteOffFormSchemaArgs) {
  return z.object({
    date: z.string().min(1, { message: requiredMsg }),
    amount: positiveAmount(requiredMsg, positiveMsg),
    notes: z.string().max(EXPENSE_NOTES_MAX).optional(),
  });
}

export type WriteOffFormValues = z.infer<ReturnType<typeof buildWriteOffFormSchema>>;

/*
 * The money settings a group holds in common: the split a new expense opens on, and whether a
 * recorded settlement is confirmed on the spot instead of waiting on the payee.
 *
 * Both are group-wide standards rather than money movement, which is why the API makes changing them
 * admin-only while every member may record an expense or a payment.
 */
export function buildMoneySettingsFormSchema(requiredMsg: string) {
  return z.object({
    defaultSplitMethod: z.enum(SPLIT_METHODS, { message: requiredMsg }),
    autoFinaliseSettlements: z.boolean(),
  });
}

export type MoneySettingsFormValues = z.infer<ReturnType<typeof buildMoneySettingsFormSchema>>;
