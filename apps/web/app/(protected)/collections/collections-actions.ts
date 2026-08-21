'use server';

import type { CollectionFormValues } from '@/app/(protected)/collections/collections-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createCollection(values: CollectionFormValues): Promise<void> {
  const res = await authenticatedFetch('/collections', {
    method: 'POST',
    body: {
      name: values.name,
      target_percentage: values.targetPercentage ? Number(values.targetPercentage) : null,
    },
  });
  if (!res.ok) throw new Error('Failed to create collection');
  const raw: { id: number } = await res.json();
  if (values.investmentIds?.length) {
    await setCollectionInvestments(raw.id, values.investmentIds);
  }
}

export async function updateCollection(id: number, values: CollectionFormValues): Promise<void> {
  const res = await authenticatedFetch(`/collections/${id}`, {
    method: 'PUT',
    body: {
      name: values.name,
      target_percentage: values.targetPercentage ? Number(values.targetPercentage) : null,
    },
  });
  if (!res.ok) throw new Error('Failed to update collection');
  await setCollectionInvestments(id, values.investmentIds ?? []);
}

export async function deleteCollection(id: number): Promise<void> {
  const res = await authenticatedFetch(`/collections/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete collection');
}

async function setCollectionInvestments(
  collectionId: number,
  investmentIds: number[],
): Promise<void> {
  const res = await authenticatedFetch(`/collections/${collectionId}/investments`, {
    method: 'PUT',
    body: { investment_ids: investmentIds },
  });
  if (!res.ok) throw new Error('Failed to set collection investments');
}
