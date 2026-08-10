'use server';

import { getTranslations } from 'next-intl/server';

import type { PaymentObligationFormValues } from '@/app/(protected)/payment-obligations/payment-obligation-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError } from '@/lib/i18n/api-errors';

function toBody(values: PaymentObligationFormValues) {
  const {
    nextDueDate,
    recurrence,
    category,
    expenseCategory,
    paymentMethod,
    creditCardId,
    defaultAccountId,
    notes,
    ...rest
  } = values;
  return {
    ...rest,
    amount: Number(values.amount),
    next_due_date: nextDueDate,
    recurrence: recurrence ?? null,
    category: category || null,
    expense_category: expenseCategory ?? null,
    payment_method: paymentMethod ?? null,
    credit_card_id: paymentMethod === 'credit_card' ? (creditCardId ?? null) : null,
    // A card-paid plan draws cash at the card settlement, never here — so the funding account is
    // dropped when the method is credit_card rather than sent for the API to refuse.
    default_account_id: paymentMethod === 'credit_card' ? null : (defaultAccountId ?? null),
    notes: notes || null,
  };
}

// Resolves a refused save to its localized reason (a default funding account in another currency, a
// card-paid plan that also names one, a mismatched card pairing, a locked field). Returned as DATA
// rather than thrown: the Server Action boundary strips prototype chains, so a thrown message is lost.
async function planError(res: Response): Promise<string> {
  const t = await getTranslations('apiErrors');
  return resolveApiError(t, await parseApiError(res), '');
}

export type SavePaymentObligationResult = { ok: true } | { ok: false; conflictDetail: string };

export async function createPaymentObligation(
  values: PaymentObligationFormValues,
): Promise<SavePaymentObligationResult> {
  const res = await authenticatedFetch('/payment-obligations', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) {
    if (res.status === 400) return { ok: false, conflictDetail: await planError(res) };
    throw new Error('Failed to create payment obligation');
  }
  return { ok: true };
}

export async function updatePaymentObligation(
  id: number,
  values: PaymentObligationFormValues,
): Promise<SavePaymentObligationResult> {
  const res = await authenticatedFetch(`/payment-obligations/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) {
    if (res.status === 400) return { ok: false, conflictDetail: await planError(res) };
    throw new Error('Failed to update payment obligation');
  }
  return { ok: true };
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

// Focused partial update for the amount-mismatch follow-up prompt after Mark Paid.
// Doesn't touch any other field — narrows the blast radius vs the full update.
export async function updatePaymentObligationAmount(id: number, amount: string): Promise<void> {
  const res = await authenticatedFetch(`/payment-obligations/${id}`, {
    method: 'PUT',
    body: { amount: Number(amount) },
  });
  if (!res.ok) throw new Error('Failed to update payment obligation amount');
}
