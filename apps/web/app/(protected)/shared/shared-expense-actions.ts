'use server';

import { toResult, type SharedMutationResult } from '@/app/(protected)/shared/mutation-result';
import type { SharedExpenseFormValues } from '@/app/(protected)/shared/shared-expense-form-schema';
import { getGroupMoneySettings } from '@/lib/api/group-settlements';
import { getPotHoldings, getPots } from '@/lib/api/pots';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { DEFAULT_SPLIT_METHOD, type SplitMethod } from '@/lib/constants/shared-expenses';

/*
 * Mutations on a group's shared expenses, plus the one read the form needs and no page can afford to
 * make eagerly.
 *
 * Every mutation returns its refusal as data through `toResult` — see `mutation-result.ts` for why —
 * and the refusals worth surfacing here are the ones a user could not have known: a split that does
 * not add up (400), a payer named alongside joint money or omitted without it (400), a funding
 * account whose pot belongs to another group or has no agreed division yet (400), an expense dated
 * before its account opened (400), and a seat, account or card that is not reachable (404).
 *
 * Amounts and figures are sent as STRINGS exactly as typed. The API's fields are Decimal, and routing
 * a money figure through a JS number is how 5.85 becomes 5.849999999999999 and gets refused by a
 * `decimal_places=2` validator for a reason the user cannot act on.
 */

// One shared account a group can spend from, for the funding picker.
export interface GroupFundingAccount {
  id: number;
  name: string;
  currency: string;
  // Which pot holds it. A group with two pots can hold two accounts with the same name — nothing
  // constrains either to be unique — so the picker needs this to tell them apart.
  potName: string | null;
}

// Everything the shared-expense form needs about a group that its caller may not already have.
export interface GroupExpenseContext {
  fundingAccounts: GroupFundingAccount[];
  defaultSplitMethod: SplitMethod;
}

/*
 * Builds the request body both writes send. Extracted because PUT is a FULL replacement of POST's
 * body rather than a patch — two copies would be two places for the funding branch to drift, and the
 * branch is the part with a rule.
 *
 * The two funding shapes are mutually exclusive in exactly the way the API requires: joint money
 * names an account and NO payer (naming one is refused rather than ignored, because silently dropping
 * a field the user filled in is how a form records something other than what it showed), while a
 * member paying names a payer and at most one instrument of their own.
 *
 * `splits` carries only the checked participants, and `figure` is omitted entirely for `equal` —
 * the API ignores it there, and sending a stale figure from a method the user switched away from
 * would put a number in a field that means nothing.
 */
function toRequestBody(values: SharedExpenseFormValues) {
  const joint = values.fundingSource === 'joint';
  return {
    date: values.date,
    amount: values.amount,
    currency: values.currency,
    category: values.category ?? null,
    notes: values.notes?.trim() || null,
    split_method: values.splitMethod,
    splits: values.splits
      .filter((split) => split.included)
      .map((split) => ({
        member_id: split.memberId,
        figure: values.splitMethod === 'equal' ? null : split.figure || null,
      })),
    payer_member_id: joint ? null : Number(values.payerMemberId),
    paid_from_account_id: joint ? Number(values.sharedAccountId) : (values.accountId ?? null),
    payment_method: joint ? null : (values.paymentMethod ?? null),
    credit_card_id: joint ? null : (values.creditCardId ?? null),
  };
}

export async function createSharedExpense(
  groupId: number,
  values: SharedExpenseFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/expenses`, {
    method: 'POST',
    body: toRequestBody(values),
  });
  return toResult(res, 'Failed to create shared expense');
}

// A full replacement, matching the API: the amount, the method and the participants are one
// interlocking statement, so changing the amount alone would leave exact figures that no longer add
// up to it and there is no honest way to infer what the user meant.
export async function updateSharedExpense(
  groupId: number,
  expenseId: number,
  values: SharedExpenseFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/expenses/${expenseId}`, {
    method: 'PUT',
    body: toRequestBody(values),
  });
  return toResult(res, 'Failed to update shared expense');
}

export async function deleteSharedExpense(
  groupId: number,
  expenseId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/expenses/${expenseId}`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to delete shared expense');
}

/*
 * What the shared-expense form needs about a group, read on demand rather than with the page.
 *
 * A read in an actions file, which is unusual and deliberate — the same shape as the expense form's
 * `getAutoChargeMatch`. Two things make it the right call. There is no endpoint that lists a group's
 * shared accounts, so assembling one costs the pots plus a holdings read per pot; and the form that
 * needs them opens on `/expenses` as well as on the group hub, where paying that cost for every group
 * a user belongs to on every page load would be real money spent on a dialog most visits never open.
 *
 * The group's default split method rides along rather than being prop-drilled, so BOTH doors into
 * this form open on the split the group actually agreed to — the hub knows it and `/expenses` does
 * not, and two sources for one default is two things that can disagree about what a group chose.
 *
 * Archived accounts are dropped: an archived account is excluded from its pot's value, so spending
 * from it would move the account and leave the pot's NAV where it was.
 *
 * A group the caller cannot reach yields an empty list rather than an error, because the pots
 * endpoint filters by the row-level policies rather than answering 404 — so the picker simply has
 * nothing to offer, which is also true of a group that has no shared account yet.
 */
export async function getGroupExpenseContext(groupId: number): Promise<GroupExpenseContext> {
  const [pots, settings] = await Promise.all([
    getPots(groupId),
    getGroupMoneySettings(groupId).catch(() => null),
  ]);
  const holdings = await Promise.all(pots.map((pot) => getPotHoldings(pot.id)));
  return {
    fundingAccounts: pots.flatMap((pot, index) =>
      (holdings[index]?.accounts ?? [])
        .filter((account) => account.isActive)
        .map((account) => ({
          id: account.id,
          name: account.name,
          currency: account.currency,
          potName: pot.name,
        })),
    ),
    defaultSplitMethod: settings?.defaultSplitMethod ?? DEFAULT_SPLIT_METHOD,
  };
}
