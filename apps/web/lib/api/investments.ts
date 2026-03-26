import 'server-only';

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
  created_at: string;
  updated_at: string;
  groups: InvestmentGroupInfo[];
}

interface InvestmentListRaw {
  items: InvestmentRaw[];
  total: number;
  page: number;
  page_size: number;
}

interface InvestmentGroupRaw {
  id: number;
  name: string;
  investment_ids: number[];
}

// --- Frontend types (camelCase) ---

export interface InvestmentGroupInfo {
  id: number;
  name: string;
}

export interface Investment {
  id: number;
  name: string;
  category: string;
  baseCurrency: string;
  ticker: string | null;
  broker: string | null;
  notes: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  groups: InvestmentGroupInfo[];
}

export interface InvestmentListResponse {
  items: Investment[];
  total: number;
  page: number;
  pageSize: number;
}

export interface InvestmentGroup {
  id: number;
  name: string;
  investmentIds: number[];
}

export type InvestmentSortField = 'name' | 'category' | 'base_currency' | 'broker';
export type SortOrder = 'asc' | 'desc';

export interface GetInvestmentsParams {
  search?: string;
  groupIds?: number[];
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
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    groups: raw.groups,
  };
}

function mapGroup(raw: InvestmentGroupRaw): InvestmentGroup {
  return {
    id: raw.id,
    name: raw.name,
    investmentIds: raw.investment_ids,
  };
}

// --- API functions ---

export async function getInvestments(
  params: GetInvestmentsParams = {},
): Promise<InvestmentListResponse> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.groupIds?.length) {
    params.groupIds.forEach((id) => qs.append('group_ids', String(id)));
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
  };
}

export async function getGroups(params?: {
  search?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}): Promise<InvestmentGroup[]> {
  const qs = new URLSearchParams();
  if (params?.search) qs.set('search', params.search);
  if (params?.sortBy) qs.set('sort_by', params.sortBy);
  if (params?.sortOrder) qs.set('sort_order', params.sortOrder);
  const endpoint = qs.toString() ? `/groups?${qs.toString()}` : '/groups';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch groups');
  const raw: InvestmentGroupRaw[] = await res.json();
  return raw.map(mapGroup);
}
