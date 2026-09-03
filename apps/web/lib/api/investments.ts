import 'server-only';

import type { InvestmentCollectionInfo } from '@/lib/api/collections';
import {
  mapListSection,
  type ListScope,
  type ListSection,
  type ListSectionRaw,
  type SortOrder,
} from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface InvestmentRaw {
  id: number;
  name: string;
  category: string;
  base_currency: string;
  ticker: string | null;
  broker: string | null;
  notes: string | null;
  is_active: boolean;
  has_snapshots: boolean;
  scope: string;
  pot_id: number | null;
  created_at: string;
  updated_at: string;
  collections: InvestmentCollectionInfo[];
}

interface InvestmentListRaw {
  items: InvestmentRaw[];
  total: number;
  page: number;
  page_size: number;
  sections: ListSectionRaw[];
}

// --- Frontend types (camelCase) ---

export interface Investment {
  id: number;
  name: string;
  category: string;
  baseCurrency: string;
  ticker: string | null;
  broker: string | null;
  notes: string | null;
  isActive: boolean;
  hasSnapshots: boolean;
  // 'shared' when a pot the caller co-owns holds it. `potId` joins the row to its section, which is
  // where the pot's label and the caller's write access are stated — once, not per row.
  scope: 'private' | 'shared';
  potId: number | null;
  createdAt: string;
  updatedAt: string;
  collections: InvestmentCollectionInfo[];
}

export interface InvestmentListResponse {
  items: Investment[];
  total: number;
  page: number;
  pageSize: number;
  sections: ListSection[];
}

export type InvestmentSortField = 'name' | 'category' | 'base_currency' | 'broker';

export interface GetInvestmentsParams {
  // Defaults to 'private' on the API, which is what keeps the four pickers that read this list
  // showing only the caller's own holdings. The list PAGE asks for 'all'.
  scope?: ListScope;
  search?: string;
  collectionIds?: number[];
  category?: string;
  activeOnly?: boolean;
  page?: number;
  pageSize?: number;
  sortBy?: InvestmentSortField;
  sortOrder?: SortOrder;
}

// --- Mappers ---

function mapInvestment(raw: InvestmentRaw): Investment {
  return {
    id: raw.id,
    name: raw.name,
    category: raw.category,
    baseCurrency: raw.base_currency,
    ticker: raw.ticker,
    broker: raw.broker,
    notes: raw.notes,
    isActive: raw.is_active,
    hasSnapshots: raw.has_snapshots,
    scope: raw.scope === 'shared' ? 'shared' : 'private',
    potId: raw.pot_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    collections: raw.collections,
  };
}

// --- API functions ---

export async function getInvestments(
  params: GetInvestmentsParams = {},
): Promise<InvestmentListResponse> {
  const qs = new URLSearchParams();
  if (params.scope) qs.set('scope', params.scope);
  if (params.search) qs.set('search', params.search);
  if (params.collectionIds?.length) {
    params.collectionIds.forEach((id) => qs.append('collection_ids', String(id)));
  }
  if (params.category) qs.set('category', params.category);
  if (params.activeOnly !== undefined) qs.set('active_only', String(params.activeOnly));
  if (params.page !== undefined) qs.set('page', String(params.page));
  if (params.pageSize !== undefined) qs.set('page_size', String(params.pageSize));
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);

  const endpoint = qs.toString() ? `/investments?${qs.toString()}` : '/investments';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch investments');
  const raw: InvestmentListRaw = await res.json();
  return {
    items: raw.items.map(mapInvestment),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
    sections: raw.sections.map(mapListSection),
  };
}
