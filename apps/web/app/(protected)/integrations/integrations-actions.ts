'use server';

import { revalidatePath } from 'next/cache';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

interface CreateApiKeyResult {
  id: number;
  name: string | null;
  rawKey: string;
}

export async function createApiKey(name: string | null): Promise<CreateApiKeyResult> {
  const res = await authenticatedFetch('/api-keys', {
    method: 'POST',
    body: { name: name || null },
  });
  if (!res.ok) throw new Error('Failed to create API key');
  const raw = await res.json();
  revalidatePath('/integrations', 'page');
  return { id: raw.id, name: raw.name, rawKey: raw.raw_key };
}

export async function revokeApiKey(keyId: number): Promise<void> {
  const res = await authenticatedFetch(`/api-keys/${keyId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to revoke API key');
  revalidatePath('/integrations', 'page');
}
