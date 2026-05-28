'use server';

import type { ExpenseFormValues } from '@/app/(protected)/expenses/expenses-form-schema';
import type { Expense } from '@/lib/api/expenses';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface ExpenseRaw {
  id: number;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  source: string;
  payment_obligation_id: number | null;
  subscription_id: number | null;
  installment_id: number | null;
  created_at: string;
  updated_at: string;
}

// Fetches a single expense by id. Used by the Payments Calendar to open the linked
// expense's edit dialog when the user clicks a Paid badge.
export async function getExpenseById(id: number): Promise<Expense> {
  const res = await authenticatedFetch(`/expenses/${id}`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch expense');
  const raw: ExpenseRaw = await res.json();
  return {
    id: raw.id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    category: raw.category,
    notes: raw.notes,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    source: raw.source,
    paymentObligationId: raw.payment_obligation_id,
    subscriptionId: raw.subscription_id,
    installmentId: raw.installment_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

export async function createExpense(values: ExpenseFormValues): Promise<void> {
  const {
    paymentMethod,
    creditCardId,
    paymentObligationId,
    subscriptionId,
    installmentId,
    ...rest
  } = values;
  const res = await authenticatedFetch('/expenses', {
    method: 'POST',
    body: {
      ...rest,
      payment_method: paymentMethod,
      credit_card_id: creditCardId,
      payment_obligation_id: paymentObligationId ?? null,
      subscription_id: subscriptionId ?? null,
      installment_id: installmentId ?? null,
    },
  });
  if (!res.ok) throw new Error('Failed to create expense');
}

export async function updateExpense(id: number, values: ExpenseFormValues): Promise<void> {
  // paymentObligationId / subscriptionId / installmentId intentionally excluded — the update
  // endpoint doesn't accept the three commitment FKs (links are set at creation only;
  // correcting an over-advance is done via the obligation / plan's own form). Reverse-on-
  // unlink semantics are deferred to the bundled reverse-advance feature (Bucket 2).
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
