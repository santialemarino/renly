import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface PaymentObligationRaw {
  id: number;
  name: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  next_due_date: string;
  recurrence: string | null;
  category: string | null;
  expense_category: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  is_active: boolean;
  notes: string | null;
  last_payment_date: string | null;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface PaymentObligation {
  id: number;
  name: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  nextDueDate: string;
  recurrence: string | null;
  category: string | null;
  expenseCategory: string | null;
  paymentMethod: string | null;
  creditCardId: number | null;
  isActive: boolean;
  notes: string | null;
  lastPaymentDate: string | null;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapObligation(raw: PaymentObligationRaw): PaymentObligation {
  return {
    id: raw.id,
    name: raw.name,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    nextDueDate: raw.next_due_date,
    recurrence: raw.recurrence,
    category: raw.category,
    expenseCategory: raw.expense_category,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    isActive: raw.is_active,
    notes: raw.notes,
    lastPaymentDate: raw.last_payment_date,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type PaymentObligationSortField =
  | 'name'
  | 'amount'
  | 'currency'
  | 'next_due_date'
  | 'recurrence'
  | 'category';
export type SortOrder = 'asc' | 'desc';

export interface GetPaymentObligationsParams {
  search?: string;
  sortBy?: PaymentObligationSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
  currency?: string;
}

export async function getPaymentObligations(
  params: GetPaymentObligationsParams = {},
): Promise<PaymentObligation[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');
  if (params.currency) qs.set('currency', params.currency);

  const endpoint = qs.toString() ? `/payment-obligations?${qs.toString()}` : '/payment-obligations';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch payment obligations');
  const raw: PaymentObligationRaw[] = await res.json();
  return raw.map(mapObligation);
}
