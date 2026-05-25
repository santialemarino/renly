'use server';

import type { ExpenseFormValues } from '@/app/(protected)/expenses/expenses-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createExpense(values: ExpenseFormValues): Promise<void> {
  const { paymentMethod, creditCardId, paymentObligationId, ...rest } = values;
  const res = await authenticatedFetch('/expenses', {
    method: 'POST',
    body: {
      ...rest,
      payment_method: paymentMethod,
      credit_card_id: creditCardId,
      payment_obligation_id: paymentObligationId ?? null,
    },
  });
  if (!res.ok) throw new Error('Failed to create expense');
}

export async function updateExpense(id: number, values: ExpenseFormValues): Promise<void> {
  // paymentObligationId intentionally excluded — the update endpoint doesn't accept the FK
  // (the link is set at creation only; correcting an over-advance is done via the
  // obligation's own form).
  const res = await authenticatedFetch(`/expenses/${id}`, {
    method: 'PUT',
    body: {
      date: values.date,
      amount: values.amount,
      currency: values.currency,
      category: values.category,
      notes: values.notes,
      payment_method: values.paymentMethod,
      credit_card_id: values.creditCardId,
    },
  });
  if (!res.ok) throw new Error('Failed to update expense');
}

export async function deleteExpense(id: number): Promise<void> {
  const res = await authenticatedFetch(`/expenses/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete expense');
}

// Result of a manual-dupe expense lookup (Phase 3, Step D).
export interface AutoChargeMatch {
  expenseId: number;
  date: string;
  source: 'subscription' | 'installment';
  sourcePlan: { id: number; name: string };
}

interface AutoChargeMatchRaw {
  expense_id: number;
  date: string;
  source: 'subscription' | 'installment';
  source_plan: { id: number; name: string };
}

export async function getAutoChargeMatch(params: {
  creditCardId: number;
  currency: string;
  amount: string;
  date: string;
  excludeExpenseId?: number;
}): Promise<AutoChargeMatch | null> {
  const qs = new URLSearchParams({
    credit_card_id: String(params.creditCardId),
    currency: params.currency,
    amount: params.amount,
    date: params.date,
  });
  if (params.excludeExpenseId !== undefined) {
    qs.set('exclude_expense_id', String(params.excludeExpenseId));
  }
  const res = await authenticatedFetch(`/expenses/auto-charge-match?${qs.toString()}`, {
    method: 'GET',
  });
  if (!res.ok) throw new Error('Failed to look up auto-charge match');
  const raw: { match: AutoChargeMatchRaw | null } = await res.json();
  if (!raw.match) return null;
  return {
    expenseId: raw.match.expense_id,
    date: raw.match.date,
    source: raw.match.source,
    sourcePlan: raw.match.source_plan,
  };
}
