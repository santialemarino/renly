import 'server-only';

import {
  mapListSection,
  type ListScope,
  type ListSection,
  type ListSectionRaw,
  type SortOrder,
} from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { EntryScope } from '@/lib/constants/entries';

// --- Raw types (API JSON shape, snake_case) ---

interface IncomeEntryRaw {
  id: number;
  scope: string;
  group_id: number | null;
  group_name: string | null;
  full_amount: string | null;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  account_id: number | null;
  source: string;
  reconciliation_id: number | null;
  account_reconciliation_id: number | null;
  created_at: string;
  updated_at: string;
}

interface IncomeListRaw {
  items: IncomeEntryRaw[];
  total: number;
  page: number;
  page_size: number;
  display_currency: string | null;
  skipped_currencies: string[];
  sections: ListSectionRaw[];
}

// --- Frontend types (camelCase) ---

export interface IncomeEntry {
  id: number;
  /*
   * Which table the row came from — 'private' for the user's own income_entries row, 'shared' for
   * their SHARE of one their group recorded, read in by the list's union.
   *
   * It is half the identity, not a label: ids are unique per table and not across them, so a shared
   * row's `id` is meaningless to /income/{id}. Every row action has to gate on this.
   */
  scope: EntryScope;
  // Set on a shared row only: the group it belongs to, and the whole amount `amount` is a share of.
  groupId: number | null;
  groupName: string | null;
  fullAmount: string | null;
  date: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  category: string | null;
  notes: string | null;
  accountId: number | null;
  source: string;
  reconciliationId: number | null;
  accountReconciliationId: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface IncomeListResponse {
  items: IncomeEntry[];
  total: number;
  page: number;
  pageSize: number;
  displayCurrency: string | null;
  // Original-currency codes on this page whose converted amount is null because no rate was stored.
  // The API has computed these since Phase 3 and nothing read them, so a row that could not be
  // converted rendered its original figure with no sign that it had not been converted at all.
  skippedCurrencies: string[];
  sections: ListSection[];
}

export type IncomeSortField = 'date' | 'amount' | 'category';

export interface GetIncomeParams {
  // Defaults to 'all' on the API, which is this list's existing behaviour: it has unioned each
  // member's share since the flow half shipped. The pill narrows it.
  scope?: ListScope;
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
    scope: raw.scope as EntryScope,
    groupId: raw.group_id,
    groupName: raw.group_name,
    fullAmount: raw.full_amount,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    category: raw.category,
    notes: raw.notes,
    accountId: raw.account_id,
    source: raw.source,
    reconciliationId: raw.reconciliation_id,
    accountReconciliationId: raw.account_reconciliation_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export async function getIncome(params: GetIncomeParams = {}): Promise<IncomeListResponse> {
  const qs = new URLSearchParams();
  if (params.scope) qs.set('scope', params.scope);
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
    skippedCurrencies: raw.skipped_currencies,
    sections: raw.sections.map(mapListSection),
  };
}
