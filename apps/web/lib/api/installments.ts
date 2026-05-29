import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface InstallmentRaw {
  id: number;
  name: string;
  total_amount: string;
  installment_amount: string;
  currency: string;
  converted_total_amount: string | null;
  converted_installment_amount: string | null;
  installments_count: number;
  current_installment: number;
  start_date: string;
  next_cuota_date: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface Installment {
  id: number;
  name: string;
  totalAmount: string;
  installmentAmount: string;
  currency: string;
  convertedTotalAmount: string | null;
  convertedInstallmentAmount: string | null;
  installmentsCount: number;
  currentInstallment: number;
  startDate: string;
  // Derived from `start_date + (current_installment - 1) months` server-side so the
  // installments table can render the next-due-date in the column where subscriptions
  // show `next_billing_date` and obligations show `next_due_date`. Null when the plan
  // is fully paid (`current_installment > installments_count`).
  nextCuotaDate: string | null;
  paymentMethod: string | null;
  creditCardId: number | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapInstallment(raw: InstallmentRaw): Installment {
  return {
    id: raw.id,
    name: raw.name,
    totalAmount: raw.total_amount,
    installmentAmount: raw.installment_amount,
    currency: raw.currency,
    convertedTotalAmount: raw.converted_total_amount,
    convertedInstallmentAmount: raw.converted_installment_amount,
    installmentsCount: raw.installments_count,
    currentInstallment: raw.current_installment,
    startDate: raw.start_date,
    nextCuotaDate: raw.next_cuota_date,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    isActive: raw.is_active,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type InstallmentSortField =
  | 'name'
  | 'total_amount'
  | 'installment_amount'
  | 'currency'
  | 'installments_count'
  | 'current_installment'
  | 'start_date'
  | 'next_cuota_date';
export type SortOrder = 'asc' | 'desc';

export interface GetInstallmentsParams {
  search?: string;
  sortBy?: InstallmentSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
  // Archived plan ids to include alongside the active set — used by the expense edit
  // dialog so a row linked to a since-archived plan can still surface in the linked-FK
  // dropdown. Server ignores when showArchived=true.
  includeIds?: number[];
  currency?: string;
}

export async function getInstallments(params: GetInstallmentsParams = {}): Promise<Installment[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');
  if (params.includeIds && params.includeIds.length > 0) {
    for (const id of params.includeIds) qs.append('include_ids', String(id));
  }
  if (params.currency) qs.set('currency', params.currency);

  const endpoint = qs.toString() ? `/installments?${qs.toString()}` : '/installments';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch installments');
  const raw: InstallmentRaw[] = await res.json();
  return raw.map(mapInstallment);
}
