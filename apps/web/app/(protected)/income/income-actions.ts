'use server';

import type { IncomeFormValues } from '@/app/(protected)/income/income-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createIncome(values: IncomeFormValues): Promise<void> {
  const res = await authenticatedFetch('/income', {
    method: 'POST',
    body: values,
  });
  if (!res.ok) throw new Error('Failed to create income entry');
}

export async function updateIncome(id: number, values: IncomeFormValues): Promise<void> {
  const res = await authenticatedFetch(`/income/${id}`, {
    method: 'PUT',
    body: values,
  });
  if (!res.ok) throw new Error('Failed to update income entry');
}

export async function deleteIncome(id: number): Promise<void> {
  const res = await authenticatedFetch(`/income/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete income entry');
}
