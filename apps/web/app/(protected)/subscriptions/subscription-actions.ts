'use server';

import { getTranslations } from 'next-intl/server';

import type { SubscriptionFormValues } from '@/app/(protected)/subscriptions/subscription-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError } from '@/lib/i18n/api-errors';

function toBody(values: SubscriptionFormValues) {
  const { billingCycle, nextBillingDate, paymentMethod, creditCardId, defaultAccountId, ...rest } =
    values;
  return {
    ...rest,
    amount: Number(values.amount),
    billing_cycle: billingCycle,
    next_billing_date: nextBillingDate,
    payment_method: paymentMethod ?? null,
    credit_card_id: paymentMethod === 'credit_card' ? (creditCardId ?? null) : null,
    // A card-paid plan draws cash at the card settlement, never here — so the funding account is
    // dropped when the method is credit_card rather than sent for the API to refuse.
    default_account_id: paymentMethod === 'credit_card' ? null : (defaultAccountId ?? null),
  };
}

// Resolves a refused save to its localized reason (a default funding account in another currency, a
// card-paid plan that also names one, a mismatched card pairing, a locked field). Returned as DATA
// rather than thrown: the Server Action boundary strips prototype chains, so a thrown message is lost.
async function planError(res: Response): Promise<string> {
  const t = await getTranslations('apiErrors');
  return resolveApiError(t, await parseApiError(res), '');
}

export type SaveSubscriptionResult = { ok: true } | { ok: false; conflictDetail: string };

export async function createSubscription(
  values: SubscriptionFormValues,
): Promise<SaveSubscriptionResult> {
  const res = await authenticatedFetch('/subscriptions', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) {
    if (res.status === 400) return { ok: false, conflictDetail: await planError(res) };
    throw new Error('Failed to create subscription');
  }
  return { ok: true };
}

export async function updateSubscription(
  id: number,
  values: SubscriptionFormValues,
): Promise<SaveSubscriptionResult> {
  const res = await authenticatedFetch(`/subscriptions/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) {
    if (res.status === 400) return { ok: false, conflictDetail: await planError(res) };
    throw new Error('Failed to update subscription');
  }
  return { ok: true };
}

export async function deleteSubscription(id: number): Promise<void> {
  const res = await authenticatedFetch(`/subscriptions/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete subscription');
}

export async function archiveSubscription(id: number): Promise<void> {
  const res = await authenticatedFetch(`/subscriptions/${id}`, {
    method: 'PUT',
    body: { is_active: false },
  });
  if (!res.ok) throw new Error('Failed to archive subscription');
}

export async function unarchiveSubscription(id: number): Promise<void> {
  const res = await authenticatedFetch(`/subscriptions/${id}`, {
    method: 'PUT',
    body: { is_active: true },
  });
  if (!res.ok) throw new Error('Failed to unarchive subscription');
}

// Focused partial update for the amount-mismatch follow-up prompt fired from the expense
// form when a manual entry linked to a subscription is saved with a different amount than
// the plan's current expected amount (Phase 3, follow-up Item 6). Doesn't touch any other
// field — narrows the blast radius vs the full update, matches the obligation precedent.
export async function updateSubscriptionAmount(id: number, amount: string): Promise<void> {
  const res = await authenticatedFetch(`/subscriptions/${id}`, {
    method: 'PUT',
    body: { amount: Number(amount) },
  });
  if (!res.ok) throw new Error('Failed to update subscription amount');
}
