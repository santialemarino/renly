'use server';

import { toResult, type SharedMutationResult } from '@/app/(protected)/shared/mutation-result';
import {
  NO_SOURCE,
  type SharedIncomeFormValues,
} from '@/app/(protected)/shared/shared-income-form-schema';
import { getGroupMoneySettings } from '@/lib/api/group-settlements';
import { getPotHoldings, getPots } from '@/lib/api/pots';
import { getSharedIncome, type SharedIncome } from '@/lib/api/shared-income';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { DEFAULT_SPLIT_METHOD, type SplitMethod } from '@/lib/constants/shared-expenses';

/*
 * Mutations on a group's shared income, plus the one read the form needs and no page can afford to
 * make eagerly. The mirror of `shared-expense-actions.ts`.
 *
 * Every mutation returns its refusal as data through `toResult` — see `mutation-result.ts` for why —
 * and the refusals worth surfacing here are the ones a user could not have known: a split that does
 * not add up (400), a destination that contradicts where the money landed (400), a shared account
 * whose pot belongs to another group or has no agreed division yet (400), a source asset this group's
 * pots do not hold (400), a row dated before its account opened (400), and a seat or account that is
 * not reachable (404).
 *
 * Amounts and figures are sent as STRINGS exactly as typed. The API's fields are Decimal, and routing
 * a money figure through a JS number is how 5.85 becomes 5.849999999999999 and gets refused by a
 * `decimal_places=2` validator for a reason the user cannot act on.
 */

// One shared account a group's income can land in, for the joint destination's picker.
export interface GroupIncomeAccount {
  id: number;
  name: string;
  currency: string;
  // Which pot holds it. A group with two pots can hold two accounts with the same name — nothing
  // constrains either to be unique — so the picker needs this to tell them apart.
  potName: string | null;
}

/*
 * One co-owned asset the income could have come from, with the proportions it is owned in.
 *
 * The shares travel WITH the asset rather than being looked up per selection, because they are what
 * F1's default split is: picking the asset has to divide the income the way that asset is divided,
 * and a second read at selection time would be a request in the middle of a form.
 */
export interface GroupIncomeSource {
  id: number;
  name: string;
  potName: string | null;
  shares: { memberId: number; percentage: string }[];
}

// Everything the shared-income form needs about a group that its caller may not already have.
export interface GroupIncomeContext {
  destinationAccounts: GroupIncomeAccount[];
  sources: GroupIncomeSource[];
  defaultSplitMethod: SplitMethod;
  /*
   * The group's income so far, newest first, which is where F2's remembered per-source default comes
   * from. Carried here rather than resolved server-side because the rule is one `find` over a list the
   * hub already renders — a stored column would need a value it cannot have before the first entry,
   * which is the argument that dropped `display_currency` in PR 5a.
   */
  history: SharedIncome[];
}

/*
 * Builds the request body both writes send. Extracted because PUT is a FULL replacement of POST's
 * body rather than a patch — two copies would be two places for the destination branch to drift, and
 * the branch is the part with a rule.
 *
 * The two destination shapes are mutually exclusive in exactly the way the API requires: joint money
 * names a shared account and NO recipient (naming one is refused rather than ignored, because
 * silently dropping a field the user filled in is how a form records something other than what it
 * showed), while distributed money names a recipient and at most that person's own account.
 *
 * `splits` carries only the checked participants, and `figure` is omitted entirely for `equal` — the
 * API ignores it there, and sending a stale figure from a method the user switched away from would put
 * a number in a field that means nothing.
 */
function toRequestBody(values: SharedIncomeFormValues) {
  const joint = values.destination === 'joint';
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
    destination: values.destination,
    source_investment_id:
      values.sourceInvestmentId === NO_SOURCE ? null : Number(values.sourceInvestmentId),
    received_by_member_id: joint ? null : Number(values.receivedByMemberId),
    paid_to_account_id: joint ? Number(values.sharedAccountId) : (values.accountId ?? null),
  };
}

export async function createSharedIncome(
  groupId: number,
  values: SharedIncomeFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/income`, {
    method: 'POST',
    body: toRequestBody(values),
  });
  return toResult(res, 'Failed to create shared income');
}

// A full replacement, matching the API: the amount, the method and the participants are one
// interlocking statement, so changing the amount alone would leave exact figures that no longer add
// up to it and there is no honest way to infer what the user meant.
export async function updateSharedIncome(
  groupId: number,
  incomeId: number,
  values: SharedIncomeFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/income/${incomeId}`, {
    method: 'PUT',
    body: toRequestBody(values),
  });
  return toResult(res, 'Failed to update shared income');
}

export async function deleteSharedIncome(
  groupId: number,
  incomeId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/income/${incomeId}`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to delete shared income');
}

/*
 * What the shared-income form needs about a group, read on demand rather than with the page.
 *
 * A read in an actions file, which is unusual and deliberate — the same shape as
 * `getGroupExpenseContext` beside it, and for the same two reasons. There is no endpoint that lists a
 * group's shared accounts or its co-owned assets, so assembling one costs the pots plus a holdings
 * read per pot; and the form that needs them opens on `/income` as well as on the group hub, where
 * paying that for every group a user belongs to on every page load would be real money spent on a
 * dialog most visits never open.
 *
 * The pots' `shares` come back on the pots read itself, so F1's default split costs nothing extra.
 *
 * Archived holdings are dropped from BOTH lists, for two different reasons that happen to agree: an
 * archived account is excluded from its pot's value, so income landing there would move the account
 * and leave the pot's NAV where it was; and an archived asset is one the group has stopped tracking,
 * so offering it as a source of new income would be odd even though the API would accept it.
 *
 * A group the caller cannot reach yields empty lists rather than an error, because the pots endpoint
 * filters by the row-level policies rather than answering 404 — so the pickers simply have nothing to
 * offer, which is also true of a group whose shared money holds nothing yet.
 */
export async function getGroupIncomeContext(groupId: number): Promise<GroupIncomeContext> {
  const [pots, settings, history] = await Promise.all([
    getPots(groupId),
    getGroupMoneySettings(groupId).catch(() => null),
    getSharedIncome(groupId).catch(() => null),
  ]);
  const holdings = await Promise.all(pots.map((pot) => getPotHoldings(pot.id)));
  return {
    destinationAccounts: pots.flatMap((pot, index) =>
      (holdings[index]?.accounts ?? [])
        .filter((account) => account.isActive)
        .map((account) => ({
          id: account.id,
          name: account.name,
          currency: account.currency,
          potName: pot.name,
        })),
    ),
    sources: pots.flatMap((pot, index) =>
      (holdings[index]?.investments ?? [])
        .filter((investment) => investment.isActive)
        .map((investment) => ({
          id: investment.id,
          name: investment.name,
          potName: pot.name,
          shares: pot.shares.map((share) => ({
            memberId: share.memberId,
            percentage: share.percentage,
          })),
        })),
    ),
    defaultSplitMethod: settings?.defaultSplitMethod ?? DEFAULT_SPLIT_METHOD,
    history: history ?? [],
  };
}
