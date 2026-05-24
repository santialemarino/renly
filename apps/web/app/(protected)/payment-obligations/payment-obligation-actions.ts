'use server';

import type { PaymentObligationFormValues } from '@/app/(protected)/payment-obligations/payment-obligation-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

function toBody(values: PaymentObligationFormValues) {
  const { nextDueDate, recurrence, category, paymentMethod, creditCardId, notes, ...rest } = values;
  return {
    ...rest,
    amount: Number(values.amount),
    next_due_date: nextDueDate,
    recurrence: recurrence ?? null,
    category: category || null,
    payment_method: paymentMethod ?? null,
    credit_card_id: paymentMethod === 'credit_card' ? (creditCardId ?? null) : null,
    notes: notes || null,
  };
}

export async function createPaymentObligation(values: PaymentObligationFormValues): Promise<void> {
  const res = await authenticatedFetch('/payment-obligations', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to create payment obligation');
}

export async function updatePaymentObligation(
  id: number,
  values: PaymentObligationFormValues,
): Promise<void> {
  const res = await authenticatedFetch(`/payment-obligations/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to update payment obligation');
}

export async function deletePaymentObligation(id: number): Promise<void> {
  const res = await authenticatedFetch(`/payment-obligations/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete payment obligation');
}

export async function archivePaymentObligation(id: number): Promise<void> {
  const res = await authenticatedFetch(`/payment-obligations/${id}`, {
    method: 'PUT',
    body: { is_active: false },
  });
  if (!res.ok) throw new Error('Failed to archive payment obligation');
}

export async function unarchivePaymentObligation(id: number): Promise<void> {
  const res = await authenticatedFetch(`/payment-obligations/${id}`, {
    method: 'PUT',
    body: { is_active: true },
  });
  if (!res.ok) throw new Error('Failed to unarchive payment obligation');
}
