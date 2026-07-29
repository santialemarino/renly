'use server';

import type { IncomeFormValues } from '@/app/(protected)/income/income-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// The API expects snake_case account_id; every other income field is a single word (camelCase ==
// snake_case), so only the account link needs remapping.
function toBody(values: IncomeFormValues) {
  const { accountId, ...rest } = values;
  return { ...rest, account_id: accountId ?? null };
}

export async function createIncome(values: IncomeFormValues): Promise<void> {
  const res = await authenticatedFetch('/income', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to create income entry');
}

export async function updateIncome(id: number, values: IncomeFormValues): Promise<void> {
  const res = await authenticatedFetch(`/income/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to update income entry');
}

export async function deleteIncome(id: number): Promise<void> {
  const res = await authenticatedFetch(`/income/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete income entry');
}
