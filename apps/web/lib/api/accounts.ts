import 'server-only';

import type { SortOrder } from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { AccountType } from '@/lib/constants/accounts';

// --- Raw types (API JSON shape, snake_case) ---

interface AccountRaw {
  id: number;
  name: string;
  type: string;
  currency: string;
  opening_balance: string;
  opening_date: string;
  balance: string;
  is_active: boolean;
  notes: string | null;
  has_links: boolean;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface Account {
  id: number;
  name: string;
  type: AccountType;
  currency: string;
  openingBalance: string;
  openingDate: string;
  balance: string;
  isActive: boolean;
  notes: string | null;
  hasLinks: boolean;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapAccount(raw: AccountRaw): Account {
  return {
    id: raw.id,
    name: raw.name,
    type: raw.type as AccountType,
    currency: raw.currency,
    openingBalance: raw.opening_balance,
    openingDate: raw.opening_date,
    balance: raw.balance,
    isActive: raw.is_active,
    notes: raw.notes,
    hasLinks: raw.has_links,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type AccountSortField = 'name' | 'type' | 'currency' | 'opening_date';

export interface GetAccountsParams {
  search?: string;
  sortBy?: AccountSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
}

export async function getAccounts(params: GetAccountsParams = {}): Promise<Account[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');

  const endpoint = qs.toString() ? `/accounts?${qs.toString()}` : '/accounts';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch accounts');
  const raw: AccountRaw[] = await res.json();
  return raw.map(mapAccount);
}
