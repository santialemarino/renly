import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface ExpenseRaw {
  id: number;
  date: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  category: string | null;
  notes: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  source: string;
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
  date: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  category: string | null;
  notes: string | null;
  paymentMethod: string | null;
  creditCardId: number | null;
  source: string;
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
export type SortOrder = 'asc' | 'desc';

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

function mapExpense(raw: ExpenseRaw): Expense {
  return {
    id: raw.id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    category: raw.category,
    notes: raw.notes,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    source: raw.source,
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
