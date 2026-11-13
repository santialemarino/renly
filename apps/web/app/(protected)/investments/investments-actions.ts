'use server';

import type { InvestmentFormValues } from '@/app/(protected)/investments/investments-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { isRefusal, localizedApiError } from '@/lib/i18n/api-errors-server';

export async function createInvestment(values: InvestmentFormValues): Promise<void> {
  const { collectionIds, baseCurrency, ...rest } = values;
  const res = await authenticatedFetch('/investments', {
    method: 'POST',
    body: { ...rest, base_currency: baseCurrency },
  });
  if (!res.ok) throw new Error('Failed to create investment');
  const raw: { id: number } = await res.json();
  if (collectionIds?.length) {
    await setInvestmentCollections(raw.id, collectionIds);
  }
}

export async function updateInvestment(id: number, values: InvestmentFormValues): Promise<void> {
  const { collectionIds, baseCurrency, ...rest } = values;
  const res = await authenticatedFetch(`/investments/${id}`, {
    method: 'PUT',
    body: { ...rest, base_currency: baseCurrency },
  });
  if (!res.ok) throw new Error('Failed to update investment');
  await setInvestmentCollections(id, collectionIds ?? []);
}

export type DeleteInvestmentResult = { ok: true } | { ok: false; conflictDetail: string };

// Deletes an investment with no history. One with snapshots or transactions comes back as a refusal
// whose localized detail the dialog shows, rather than as a thrown error.
export async function deleteInvestment(id: number): Promise<DeleteInvestmentResult> {
  const res = await authenticatedFetch(`/investments/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const detail = isRefusal(res) ? await localizedApiError(res) : null;
    if (detail) return { ok: false, conflictDetail: detail };
    throw new Error('Failed to delete investment');
  }
  return { ok: true };
}

export async function archiveInvestment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/investments/${id}/archive`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to archive investment');
}

export async function unarchiveInvestment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/investments/${id}/unarchive`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to unarchive investment');
}

async function setInvestmentCollections(id: number, collectionIds: number[]): Promise<void> {
  const res = await authenticatedFetch(`/investments/${id}/collections`, {
    method: 'PUT',
    body: { collection_ids: collectionIds },
  });
  if (!res.ok) throw new Error('Failed to update investment collections');
}
