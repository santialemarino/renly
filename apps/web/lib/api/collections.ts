import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface InvestmentCollectionRaw {
  id: number;
  name: string;
  target_percentage: number | null;
  investment_ids: number[];
}

// --- Frontend types (camelCase) ---

/*
 * The minimal shape embedded in an investment response. Lives here rather than in
 * `lib/api/investments.ts` because it is a collection, not an investment — and the API returns
 * the identical `{ id, name }` object on both sides, so one declaration serves both.
 */
export interface InvestmentCollectionInfo {
  id: number;
  name: string;
}

export interface InvestmentCollection {
  id: number;
  name: string;
  targetPercentage: number | null;
  investmentIds: number[];
}

// --- Mappers ---

function mapCollection(raw: InvestmentCollectionRaw): InvestmentCollection {
  return {
    id: raw.id,
    name: raw.name,
    targetPercentage: raw.target_percentage,
    investmentIds: raw.investment_ids,
  };
}

// --- API functions ---

export async function getCollections(params?: {
  search?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}): Promise<InvestmentCollection[]> {
  const qs = new URLSearchParams();
  if (params?.search) qs.set('search', params.search);
  if (params?.sortBy) qs.set('sort_by', params.sortBy);
  if (params?.sortOrder) qs.set('sort_order', params.sortOrder);
  const endpoint = qs.toString() ? `/collections?${qs.toString()}` : '/collections';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch collections');
  const raw: InvestmentCollectionRaw[] = await res.json();
  return raw.map(mapCollection);
}
