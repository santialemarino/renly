'use server';

import type { ExpenseFormValues } from '@/app/(protected)/expenses/expenses-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createExpense(values: ExpenseFormValues): Promise<void> {
  const { paymentMethod, creditCardId, ...rest } = values;
  const res = await authenticatedFetch('/expenses', {
    method: 'POST',
    body: {
      ...rest,
      payment_method: paymentMethod,
      credit_card_id: creditCardId,
    },
  });
  if (!res.ok) throw new Error('Failed to create expense');
}

export async function updateExpense(id: number, values: ExpenseFormValues): Promise<void> {
  const { paymentMethod, creditCardId, ...rest } = values;
  const res = await authenticatedFetch(`/expenses/${id}`, {
    method: 'PUT',
    body: {
      ...rest,
      payment_method: paymentMethod,
      credit_card_id: creditCardId,
    },
  });
  if (!res.ok) throw new Error('Failed to update expense');
}

export async function deleteExpense(id: number): Promise<void> {
  const res = await authenticatedFetch(`/expenses/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete expense');
}
