'use server';

import { getTranslations } from 'next-intl/server';

import type { AccountFormValues } from '@/app/(protected)/accounts/account-form-schema';
import type { AccountReconcileFormValues } from '@/app/(protected)/accounts/account-reconcile-form-schema';
import {
  mapAccountReconciliation,
  type AccountReconciliation,
} from '@/lib/api/account-reconciliations';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError } from '@/lib/i18n/api-errors';

function toBody(values: AccountFormValues) {
  const { openingBalance, openingDate, notes, ...rest } = values;
  return {
    ...rest,
    opening_balance: Number(openingBalance || 0),
    opening_date: openingDate,
    notes: notes || null,
  };
}

export async function createAccount(values: AccountFormValues): Promise<void> {
  const res = await authenticatedFetch('/accounts', { method: 'POST', body: toBody(values) });
  if (!res.ok) throw new Error('Failed to create account');
}

export async function updateAccount(id: number, values: AccountFormValues): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}`, { method: 'PUT', body: toBody(values) });
  if (!res.ok) throw new Error('Failed to update account');
}

export async function deleteAccount(id: number): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete account');
}

export async function archiveAccount(id: number): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}/archive`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to archive account');
}

export async function unarchiveAccount(id: number): Promise<void> {
  const res = await authenticatedFetch(`/accounts/${id}/unarchive`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to unarchive account');
}

// Drives the Reconciliations sub-section in the expandable account row.
export async function fetchAccountReconciliations(
  accountId: number,
): Promise<AccountReconciliation[]> {
  const res = await authenticatedFetch(`/accounts/${accountId}/reconciliations`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch reconciliations');
  const raw = await res.json();
  return raw.map(mapAccountReconciliation);
}

// The account's derived balance at a date, for the reconcile dialog's difference preview.
export async function fetchAccountComputedBalance(
  accountId: number,
  asOfDate: string,
): Promise<string> {
  const res = await authenticatedFetch(
    `/accounts/${accountId}/computed-balance?as_of_date=${encodeURIComponent(asOfDate)}`,
    { method: 'GET' },
  );
  if (!res.ok) throw new Error('Failed to fetch computed balance');
  const raw = await res.json();
  return raw.balance as string;
}

// Reconcile an account against its real balance. Returns the localized message on a rejected date
// (in the future, or before the account opened) so the dialog can surface it inline.
export async function reconcileAccount(
  accountId: number,
  values: AccountReconcileFormValues,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const res = await authenticatedFetch(`/accounts/${accountId}/reconciliations`, {
    method: 'POST',
    body: {
      as_of_date: values.asOfDate,
      statement_balance: Number(values.statementBalance),
    },
  });
  if (!res.ok) {
    const t = await getTranslations('apiErrors');
    return { ok: false, error: resolveApiError(t, await parseApiError(res), '') };
  }
  return { ok: true };
}

export async function deleteAccountReconciliation(
  accountId: number,
  reconciliationId: number,
): Promise<void> {
  const res = await authenticatedFetch(
    `/accounts/${accountId}/reconciliations/${reconciliationId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error('Failed to delete reconciliation');
}
