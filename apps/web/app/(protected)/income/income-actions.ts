'use server';

import type { IncomeFormValues } from '@/app/(protected)/income/income-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { isRefusal, localizedApiError } from '@/lib/i18n/api-errors-server';

// The API expects snake_case account_id; every other income field is a single word (camelCase ==
// snake_case), so only the account link needs remapping.
function toBody(values: IncomeFormValues) {
  const { accountId, ...rest } = values;
  return { ...rest, account_id: accountId ?? null };
}

// Discriminated result so the delete dialog can surface the backend's 409 detail — an income entry a
// reconciliation owns is refused with reconciliation_owned_entry. Returned as data rather than thrown
// because the Server Action boundary strips prototype chains (see expenses-actions for the long form).
export type IncomeMutationResult = { ok: true } | { ok: false; conflictDetail: string };

export async function createIncome(values: IncomeFormValues): Promise<void> {
  const res = await authenticatedFetch('/income', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to create income entry');
}

export async function updateIncome(
  id: number,
  values: IncomeFormValues,
): Promise<IncomeMutationResult> {
  const res = await authenticatedFetch(`/income/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to update income entry');
  }
  return { ok: true };
}

export async function deleteIncome(id: number): Promise<IncomeMutationResult> {
  const res = await authenticatedFetch(`/income/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to delete income entry');
  }
  return { ok: true };
}
