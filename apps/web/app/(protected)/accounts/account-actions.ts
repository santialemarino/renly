'use server';

import { getTranslations } from 'next-intl/server';

import type { AccountFormValues } from '@/app/(protected)/accounts/account-form-schema';
import type { AccountReconcileFormValues } from '@/app/(protected)/accounts/account-reconcile-form-schema';
import type { TransferFormValues } from '@/app/(protected)/accounts/transfer-form-schema';
import {
  mapAccountComputedBalance,
  mapAccountReconciliation,
  type AccountReconciliation,
} from '@/lib/api/account-reconciliations';
import { mapTransferList, type Transfer } from '@/lib/api/transfers';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError, type ApiError } from '@/lib/i18n/api-errors';
import { getFormatters } from '@/lib/i18n/formatters-server';

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
  return mapAccountComputedBalance(await res.json()).balance;
}

/*
 * The reconciliation errors carry dates as ISO strings (the API is locale-agnostic by contract), so
 * format them before interpolation — otherwise the message reads "…up to 2026-07-20" next to a page
 * that renders every other date as "Jul 20, 2026". Scoped here because these are the only mapped
 * `apiErrors` codes with a date param; if others gain one, move this into `lib/i18n/api-errors`.
 */
async function localizeDateParams(error: ApiError): Promise<ApiError> {
  const fmt = await getFormatters();
  const params = Object.fromEntries(
    Object.entries(error.params).map(([key, value]) =>
      key.endsWith('_date') && typeof value === 'string' ? [key, fmt.date(value)] : [key, value],
    ),
  );
  return { ...error, params };
}

// Resolves a failed reconciliation response to a localized message for the dialog / toast.
async function reconciliationError(res: Response): Promise<string> {
  const t = await getTranslations('apiErrors');
  return resolveApiError(t, await localizeDateParams(await parseApiError(res)), '');
}

// Resolves a refused transfer to its localized reason (same account, mismatched single-currency
// amounts, or a missing cross-currency amount).
async function transferError(res: Response): Promise<string> {
  const t = await getTranslations('apiErrors');
  return resolveApiError(t, await parseApiError(res), '');
}

// Reconcile an account against its real balance. Returns the localized message on a rejected date
// (in the future, before the account opened, or older than the account's latest reconciliation) so
// the dialog can surface it inline.
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
  if (!res.ok) return { ok: false, error: await reconciliationError(res) };
  return { ok: true };
}

// Delete a reconciliation. Returns the localized message when the API refuses (only the account's
// most recent reconciliation may be deleted), so the dialog can report the reason.
export async function deleteAccountReconciliation(
  accountId: number,
  reconciliationId: number,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const res = await authenticatedFetch(
    `/accounts/${accountId}/reconciliations/${reconciliationId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) return { ok: false, error: await reconciliationError(res) };
  return { ok: true };
}

// --- Transfers ---

// Transfers touching one account, on either leg — an account's history must show money arriving as
// well as leaving.
export async function fetchAccountTransfers(accountId: number): Promise<Transfer[]> {
  const res = await authenticatedFetch(`/transfers?account_id=${accountId}`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch transfers');
  return mapTransferList(await res.json());
}

/*
 * Create a transfer between two of the user's accounts. Returns the localized message when the API
 * refuses — the two accounts are the same, a single-currency transfer credits a different amount than
 * it debits, or a cross-currency transfer omits the credited amount — so the dialog can surface it
 * inline rather than as a generic failure. toAmount is sent only when the user supplied it; the API
 * mirrors fromAmount within one currency and requires it across two.
 */
export async function createTransfer(
  values: TransferFormValues,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const res = await authenticatedFetch('/transfers', {
    method: 'POST',
    body: {
      from_account_id: values.fromAccountId,
      to_account_id: values.toAccountId,
      date: values.date,
      from_amount: Number(values.fromAmount),
      to_amount: values.toAmount ? Number(values.toAmount) : null,
      notes: values.notes || null,
    },
  });
  if (!res.ok) return { ok: false, error: await transferError(res) };
  return { ok: true };
}

// Delete a transfer. Both accounts' balances recompute from the remaining rows.
export async function deleteTransfer(
  transferId: number,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const res = await authenticatedFetch(`/transfers/${transferId}`, { method: 'DELETE' });
  if (!res.ok) return { ok: false, error: await transferError(res) };
  return { ok: true };
}
