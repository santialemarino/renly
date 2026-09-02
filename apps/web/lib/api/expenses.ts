import 'server-only';

import type { SortOrder } from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { EntryScope } from '@/lib/constants/entries';

// --- Raw types (API JSON shape, snake_case) ---

/*
 * Exported (unlike the other raw types) because the colocated expense server actions need the same
 * wire shape: they extend it for the mutation responses (`advance_change` / `reverse_change`) and
 * re-use mapExpense below. One declaration of the shape and one mapper, so a new API field cannot
 * reach one call site and silently miss the other.
 */
export interface ExpenseRaw {
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
  payment_method: string | null;
  credit_card_id: number | null;
  account_id: number | null;
  source: string;
  payment_obligation_id: number | null;
  subscription_id: number | null;
  installment_id: number | null;
  reconciliation_id: number | null;
  account_reconciliation_id: number | null;
  created_at: string;
  updated_at: string;
}

interface ExpenseListRaw {
  items: ExpenseRaw[];
  total: number;
  page: number;
  page_size: number;
  display_currency: string | null;
}

// --- Frontend types (camelCase) ---

export interface Expense {
  id: number;
  /*
   * Which table the row came from — 'private' for the user's own expense_entries row, 'shared' for
   * their SHARE of one their group recorded, read in by the list's union.
   *
   * It is half the identity, not a label: ids are unique per table and not across them, so a shared
   * row's `id` is meaningless to /expenses/{id}. Every row action has to gate on this.
   */
  scope: EntryScope;
  // Set on a shared row only: the group it belongs to, and the whole expense `amount` is a share of.
  groupId: number | null;
  groupName: string | null;
  fullAmount: string | null;
  date: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  category: string | null;
  notes: string | null;
  paymentMethod: string | null;
  creditCardId: number | null;
  accountId: number | null;
  source: string;
  paymentObligationId: number | null;
  subscriptionId: number | null;
  installmentId: number | null;
  reconciliationId: number | null;
  accountReconciliationId: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface ExpenseListResponse {
  items: Expense[];
  total: number;
  page: number;
  pageSize: number;
  displayCurrency: string | null;
}

export type ExpenseSortField = 'date' | 'amount' | 'category' | 'payment_method';

export interface GetExpensesParams {
  search?: string;
  category?: string;
  paymentMethod?: string;
  dateFrom?: string;
  dateTo?: string;
  currency?: string;
  page?: number;
  pageSize?: number;
  sortBy?: ExpenseSortField;
  sortOrder?: SortOrder;
}

// --- Mappers ---

// Exported alongside ExpenseRaw so the expense server actions map identically — see the note there.
export function mapExpense(raw: ExpenseRaw): Expense {
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
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    accountId: raw.account_id,
    source: raw.source,
    paymentObligationId: raw.payment_obligation_id,
    subscriptionId: raw.subscription_id,
    installmentId: raw.installment_id,
    reconciliationId: raw.reconciliation_id,
    accountReconciliationId: raw.account_reconciliation_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export async function getExpenses(params: GetExpensesParams = {}): Promise<ExpenseListResponse> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.category) qs.set('category', params.category);
  if (params.paymentMethod) qs.set('payment_method', params.paymentMethod);
  if (params.dateFrom) qs.set('date_from', params.dateFrom);
  if (params.dateTo) qs.set('date_to', params.dateTo);
  if (params.currency) qs.set('currency', params.currency);
  if (params.page !== undefined) qs.set('page', String(params.page));
  if (params.pageSize !== undefined) qs.set('page_size', String(params.pageSize));
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);

  const endpoint = qs.toString() ? `/expenses?${qs.toString()}` : '/expenses';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch expenses');
  const raw: ExpenseListRaw = await res.json();
  return {
    items: raw.items.map(mapExpense),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
    displayCurrency: raw.display_currency,
  };
}
