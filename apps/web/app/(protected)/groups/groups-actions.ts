'use server';

import type { GroupFormValues } from '@/app/(protected)/groups/groups-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

export async function createGroup(values: GroupFormValues): Promise<void> {
  const res = await authenticatedFetch('/groups', {
    method: 'POST',
    body: { name: values.name },
  });
  if (!res.ok) throw new Error('Failed to create group');
  const raw: { id: number } = await res.json();
  if (values.investmentIds?.length) {
    await setGroupInvestments(raw.id, values.investmentIds);
  }
}

export async function updateGroup(id: number, values: GroupFormValues): Promise<void> {
  const res = await authenticatedFetch(`/groups/${id}`, {
    method: 'PUT',
    body: { name: values.name },
  });
  if (!res.ok) throw new Error('Failed to update group');
  await setGroupInvestments(id, values.investmentIds ?? []);
}

export async function deleteGroup(id: number): Promise<void> {
  const res = await authenticatedFetch(`/groups/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete group');
}

async function setGroupInvestments(groupId: number, investmentIds: number[]): Promise<void> {
  const res = await authenticatedFetch(`/groups/${groupId}/investments`, {
    method: 'PUT',
    body: { investment_ids: investmentIds },
  });
  if (!res.ok) throw new Error('Failed to set group investments');
}
