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
  | 'start_date';
export type SortOrder = 'asc' | 'desc';

export interface GetInstallmentsParams {
  search?: string;
  sortBy?: InstallmentSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
  currency?: string;
}

export async function getInstallments(params: GetInstallmentsParams = {}): Promise<Installment[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');
  if (params.currency) qs.set('currency', params.currency);

  const endpoint = qs.toString() ? `/installments?${qs.toString()}` : '/installments';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch installments');
  const raw: InstallmentRaw[] = await res.json();
  return raw.map(mapInstallment);
}
