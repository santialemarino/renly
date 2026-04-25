'use server';

import type { SubscriptionFormValues } from '@/app/(protected)/subscriptions/subscription-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

function toBody(values: SubscriptionFormValues) {
  const { billingCycle, nextBillingDate, paymentMethod, creditCardId, ...rest } = values;
  return {
    ...rest,
    amount: Number(values.amount),
    billing_cycle: billingCycle,
    next_billing_date: nextBillingDate,
    payment_method: paymentMethod ?? null,
    credit_card_id: paymentMethod === 'credit_card' ? (creditCardId ?? null) : null,
  };
}

export async function createSubscription(values: SubscriptionFormValues): Promise<void> {
  const res = await authenticatedFetch('/subscriptions', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to create subscription');
}

export async function updateSubscription(
  id: number,
  values: SubscriptionFormValues,
): Promise<void> {
  const res = await authenticatedFetch(`/subscriptions/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to update subscription');
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
