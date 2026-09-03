import 'server-only';

import {
  mapListSection,
  type ListScope,
  type ListSection,
  type ListSectionRaw,
  type SortOrder,
} from '@/lib/api/types';
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
  last_reconciled_date: string | null;
  scope: string;
  pot_id: number | null;
  created_at: string;
  updated_at: string;
}

interface AccountListRaw {
  items: AccountRaw[];
  sections: ListSectionRaw[];
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
  lastReconciledDate: string | null;
  // 'shared' when a pot the caller co-owns holds it. `potId` joins the row to its section, which is
  // where the pot's label and the caller's write access are stated — once, not per row.
  scope: 'private' | 'shared';
  potId: number | null;
  createdAt: string;
  updatedAt: string;
}

/*
 * The accounts list. An envelope rather than a bare array, because a grouped list has to say what its
 * sections are called and what each one totals — facts about the list, not about any row.
 *
 * Every existing caller reads `.items` and every one of them wants the DEFAULT scope, which is the
 * caller's own accounts: seven pages read this list as a picker, and offering a group's bank account
 * where somebody is choosing which of their own to pay from would be wrong in most of them.
 */
export interface AccountListResponse {
  items: Account[];
  sections: ListSection[];
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
    lastReconciledDate: raw.last_reconciled_date,
    scope: raw.scope === 'shared' ? 'shared' : 'private',
    potId: raw.pot_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type AccountSortField = 'name' | 'type' | 'currency' | 'opening_date';

export interface GetAccountsParams {
  // Defaults to 'private' on the API, which is what keeps the seven pickers that read this list
  // showing only the caller's own accounts. The list PAGE asks for 'all'.
  scope?: ListScope;
  search?: string;
  sortBy?: AccountSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
}

/*
 * The accounts list, grouped by scope — the list PAGE's read, and the only caller that wants the
 * sections. Asks for `all` unless told otherwise, because a grouped page is what X2 specifies.
 */
export async function getAccountsGrouped(
  params: GetAccountsParams = {},
): Promise<AccountListResponse> {
  const qs = new URLSearchParams();
  qs.set('scope', params.scope ?? 'all');
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');

  const res = await authenticatedFetch(`/accounts?${qs.toString()}`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch accounts');
  const raw: AccountListRaw = await res.json();
  return { items: raw.items.map(mapAccount), sections: raw.sections.map(mapListSection) };
}

/*
 * Just the rows, in the caller's OWN scope — what the seven pages that render an account PICKER want,
 * and the reason the API's default is `private`: offering a group's bank account where somebody is
 * choosing which of their own to pay from would be wrong in nearly all of them.
 *
 * A thin projection of the function above rather than a second read, so there is ONE raw type and ONE
 * mapper: two copies of a wire shape means the next field reaches one call site and misses the other.
 */
export async function getAccounts(params: GetAccountsParams = {}): Promise<Account[]> {
  return (await getAccountsGrouped({ ...params, scope: params.scope ?? 'private' })).items;
}

// One account with its derived balance. Returns null for an id that isn't the caller's, so the
// ledger page can render a real 404 rather than leaking that the account exists for someone else.
export async function getAccount(accountId: number): Promise<Account | null> {
  const res = await authenticatedFetch(`/accounts/${accountId}`, { method: 'GET' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to fetch account');
  const raw: AccountRaw = await res.json();
  return mapAccount(raw);
}
