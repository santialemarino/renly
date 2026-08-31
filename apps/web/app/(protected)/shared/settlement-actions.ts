'use server';

import { toResult, type SharedMutationResult } from '@/app/(protected)/shared/mutation-result';
import type {
  MoneySettingsFormValues,
  SettlementFormValues,
  SettlementLegFormValues,
  WriteOffFormValues,
} from '@/app/(protected)/shared/settlement-form-schema';
import { legCrossesCurrency } from '@/app/(protected)/shared/settlement-rules';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

/*
 * Mutations on a group's settlements and on the money settings it holds in common.
 *
 * Every one returns its refusal as data through `toResult` — see `mutation-result.ts` — and the
 * refusals worth surfacing are the ones a stale page produces or a rule the user could not have
 * known: somebody else confirmed it while this page was open (409), only the payee may confirm or
 * un-confirm (403), only the creditor may write a balance off (403), a write-off has no leg to
 * attach an account to (409), a leg naming the other party's account (400), and a cross-currency leg
 * that does not say how much moved (400).
 *
 * Amounts are sent as STRINGS exactly as typed, for the reason every money path in this module keeps
 * them: a JS number is how 5.85 becomes 5.849999999999999 and is refused by a `decimal_places=2`
 * validator for a reason the user cannot act on.
 */

/*
 * The caller's own cash leg, as the API takes it: the account, and what moved through it.
 *
 * The amount is sent ONLY across currencies. Within one currency the account moved exactly what came
 * off the bucket, and the API refuses a second figure rather than quietly preferring it — so sending
 * the same number twice is not redundancy, it is a way to be refused
 * (400 group_settlement_leg_amounts_must_match).
 *
 * An empty account clears the leg, which is why both fields go to null together: an amount with no
 * account behind it is refused outright (400 group_settlement_leg_without_account).
 *
 * One helper rather than a copy in each of the two writes that carry a leg — the rule about when the
 * figure exists is exactly the thing the two must not disagree about.
 */
function toLegBody(
  values: { accountId?: string; legCurrency?: string; legAmount?: string },
  bucketCurrency: string,
): { accountId: number | null; amount: string | null } {
  if (!values.accountId) return { accountId: null, amount: null };
  return {
    accountId: Number(values.accountId),
    amount: legCrossesCurrency(values.legCurrency, bucketCurrency)
      ? (values.legAmount ?? null)
      : null,
  };
}

/*
 * Records a payment one member made to another.
 *
 * ANY member may record one — either side of a payment can be the one who remembers to write it
 * down, and the API asks only for membership. What the caller's seat decides is whether a cash leg
 * can be attached at all, and which of the two it lands on; a request naming the other party's side
 * is refused, because the row-level policies genuinely hide those accounts.
 *
 * The leg is therefore sent on the side the caller holds, and on neither when they hold neither.
 */
export async function recordSettlement(
  groupId: number,
  currency: string,
  values: SettlementFormValues,
  side: 'outgoing' | 'incoming' | null,
): Promise<SharedMutationResult> {
  const leg = toLegBody(values, currency);
  const res = await authenticatedFetch(`/groups/${groupId}/settlements`, {
    method: 'POST',
    body: {
      from_member_id: Number(values.fromMemberId),
      to_member_id: Number(values.toMemberId),
      date: values.date,
      amount: values.amount,
      currency,
      from_account_id: side === 'outgoing' ? leg.accountId : null,
      from_amount: side === 'outgoing' ? leg.amount : null,
      to_account_id: side === 'incoming' ? leg.accountId : null,
      to_amount: side === 'incoming' ? leg.amount : null,
      notes: values.notes?.trim() || null,
    },
  });
  return toResult(res, 'Failed to record settlement');
}

// Records a debt the creditor has given up on. It clears the same bucket a payment would and moves no
// money, so it names no account and carries no leg. Only the creditor may (403 otherwise).
export async function recordWriteOff(
  groupId: number,
  fromMemberId: number,
  toMemberId: number,
  currency: string,
  values: WriteOffFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/settlements/write-off`, {
    method: 'POST',
    body: {
      from_member_id: fromMemberId,
      to_member_id: toMemberId,
      date: values.date,
      amount: values.amount,
      currency,
      notes: values.notes?.trim() || null,
    },
  });
  return toResult(res, 'Failed to write off balance');
}

// Acknowledges receipt. The payee's alone — it is the trust anchor for real money, and it means
// "I got this".
export async function confirmSettlement(
  groupId: number,
  settlementId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/settlements/${settlementId}/confirm`, {
    method: 'POST',
  });
  return toResult(res, 'Failed to confirm settlement');
}

// Takes the confirmation back, returning the settlement to pending so it can be corrected or removed.
// The payee's alone for the same reason: it is their word being withdrawn.
export async function unconfirmSettlement(
  groupId: number,
  settlementId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/settlements/${settlementId}/confirm`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to un-confirm settlement');
}

/*
 * Attaches or clears the caller's OWN cash leg. Which side it lands on follows from which seat they
 * hold, so nothing in the body names a side and nothing can name the other person's.
 *
 * Allowed on a confirmed settlement, unlike deletion: what confirmation vouches for is the amount and
 * the fact of the payment, and neither changes here — only which of the caller's own accounts it
 * passed through, which moves nobody else's balance.
 */
export async function setSettlementLeg(
  groupId: number,
  settlementId: number,
  bucketCurrency: string,
  values: SettlementLegFormValues,
): Promise<SharedMutationResult> {
  const leg = toLegBody(values, bucketCurrency);
  const res = await authenticatedFetch(`/groups/${groupId}/settlements/${settlementId}/account`, {
    method: 'PUT',
    body: { account_id: leg.accountId, amount: leg.amount },
  });
  return toResult(res, 'Failed to update settlement account');
}

// Removes a settlement — which is what reversing one is. Either named member may while it is
// pending; a write-off only its creditor; a confirmed one nobody, until the payee un-confirms it.
export async function deleteSettlement(
  groupId: number,
  settlementId: number,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/settlements/${settlementId}`, {
    method: 'DELETE',
  });
  return toResult(res, 'Failed to delete settlement');
}

// Changes the standard the group holds itself to. Admin only (403 otherwise) — setting it is
// management, not money movement, which is why every member may still record an expense or a payment.
export async function updateGroupMoneySettings(
  groupId: number,
  values: MoneySettingsFormValues,
): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/groups/${groupId}/money-settings`, {
    method: 'PUT',
    body: {
      default_split_method: values.defaultSplitMethod,
      auto_finalise_settlements: values.autoFinaliseSettlements,
    },
  });
  return toResult(res, 'Failed to update money settings');
}
