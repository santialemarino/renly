'use server';

import type { InvestmentFormValues } from '@/app/(protected)/investments/investments-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createInvestment(values: InvestmentFormValues): Promise<void> {
  const { groupIds, baseCurrency, ...rest } = values;
  const res = await authenticatedFetch('/investments', {
    method: 'POST',
    body: { ...rest, base_currency: baseCurrency },
  });
  if (!res.ok) throw new Error('Failed to create investment');
  const raw: { id: number } = await res.json();
  if (groupIds?.length) {
    await setInvestmentGroups(raw.id, groupIds);
  }
}

export async function updateInvestment(id: number, values: InvestmentFormValues): Promise<void> {
  const { groupIds, baseCurrency, ...rest } = values;
  const res = await authenticatedFetch(`/investments/${id}`, {
    method: 'PUT',
    body: { ...rest, base_currency: baseCurrency },
  });
  if (!res.ok) throw new Error('Failed to update investment');
  await setInvestmentGroups(id, groupIds ?? []);
}

export async function archiveInvestment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/investments/${id}/archive`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to archive investment');
}

export async function unarchiveInvestment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/investments/${id}/unarchive`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to unarchive investment');
}

async function setInvestmentGroups(id: number, groupIds: number[]): Promise<void> {
  const res = await authenticatedFetch(`/investments/${id}/groups`, {
    method: 'PUT',
    body: { group_ids: groupIds },
  });
  if (!res.ok) throw new Error('Failed to update investment groups');
}
