import 'server-only';

import type { SortOrder } from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface IncomeEntryRaw {
  id: number;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  source: string;
  created_at: string;
  updated_at: string;
}

interface IncomeListRaw {
  items: IncomeEntryRaw[];
  total: number;
  page: number;
  page_size: number;
  display_currency: string | null;
}

// --- Frontend types (camelCase) ---

export interface IncomeEntry {
  id: number;
  date: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  category: string | null;
  notes: string | null;
  source: string;
  createdAt: string;
  updatedAt: string;
}

export interface IncomeListResponse {
  items: IncomeEntry[];
  total: number;
  page: number;
  pageSize: number;
  displayCurrency: string | null;
}

export type IncomeSortField = 'date' | 'amount' | 'category';

export interface GetIncomeParams {
  search?: string;
  category?: string;
  dateFrom?: string;
  dateTo?: string;
  currency?: string;
  page?: number;
  pageSize?: number;
  sortBy?: IncomeSortField;
  sortOrder?: SortOrder;
}

// --- Mappers ---

function mapIncomeEntry(raw: IncomeEntryRaw): IncomeEntry {
  return {
    id: raw.id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    category: raw.category,
    notes: raw.notes,
    source: raw.source,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export async function getIncome(params: GetIncomeParams = {}): Promise<IncomeListResponse> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.category) qs.set('category', params.category);
  if (params.dateFrom) qs.set('date_from', params.dateFrom);
  if (params.dateTo) qs.set('date_to', params.dateTo);
  if (params.currency) qs.set('currency', params.currency);
  if (params.page !== undefined) qs.set('page', String(params.page));
  if (params.pageSize !== undefined) qs.set('page_size', String(params.pageSize));
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);

  const endpoint = qs.toString() ? `/income?${qs.toString()}` : '/income';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch income');
  const raw: IncomeListRaw = await res.json();
  return {
    items: raw.items.map(mapIncomeEntry),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
    displayCurrency: raw.display_currency,
  };
}
