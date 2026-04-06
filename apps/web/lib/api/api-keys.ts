import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface ApiKeyRaw {
  id: number;
  name: string | null;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

// --- Frontend types (camelCase) ---

export interface ApiKey {
  id: number;
  name: string | null;
  createdAt: string;
  lastUsedAt: string | null;
  isActive: boolean;
}

// --- Mappers ---

function mapApiKey(raw: ApiKeyRaw): ApiKey {
  return {
    id: raw.id,
    name: raw.name,
    createdAt: raw.created_at,
    lastUsedAt: raw.last_used_at,
    isActive: raw.is_active,
  };
}

// --- API functions ---

export async function getApiKeys(): Promise<ApiKey[]> {
  const res = await authenticatedFetch('/api-keys', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch API keys');
  const raw: ApiKeyRaw[] = await res.json();
  return raw.map(mapApiKey);
}
