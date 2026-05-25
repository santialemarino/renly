import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface PaymentsCalendarItemRaw {
  type: string;
  date: string;
  name: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  payment_method: string | null;
  credit_card_id: number | null;
  source_id: number;
  cuota_index: number | null;
  installments_count: number | null;
  recurrence: string | null;
  is_paid: boolean;
}

interface PaymentsCalendarRaw {
  year: number;
  month: number;
  currency: string | null;
  items: PaymentsCalendarItemRaw[];
}

// --- Frontend types (camelCase) ---

export type CalendarItemType = 'subscription' | 'installment' | 'obligation' | 'card_due';

export interface PaymentsCalendarItem {
  type: CalendarItemType;
  date: string;
  name: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  paymentMethod: string | null;
  creditCardId: number | null;
  sourceId: number;
  cuotaIndex: number | null;
  installmentsCount: number | null;
  recurrence: string | null;
  isPaid: boolean;
}

export interface PaymentsCalendar {
  year: number;
  month: number;
  currency: string | null;
  items: PaymentsCalendarItem[];
}

// --- Mappers ---

function mapItem(raw: PaymentsCalendarItemRaw): PaymentsCalendarItem {
  return {
    type: raw.type as CalendarItemType,
    date: raw.date,
    name: raw.name,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    sourceId: raw.source_id,
    cuotaIndex: raw.cuota_index,
    installmentsCount: raw.installments_count,
    recurrence: raw.recurrence,
    isPaid: raw.is_paid,
  };
}

// --- API functions ---

export interface GetPaymentsCalendarParams {
  year: number;
  month: number;
  currency?: string;
}

export async function getPaymentsCalendar(
  params: GetPaymentsCalendarParams,
): Promise<PaymentsCalendar> {
  const qs = new URLSearchParams();
  qs.set('year', String(params.year));
  qs.set('month', String(params.month));
  if (params.currency) qs.set('currency', params.currency);

  const res = await authenticatedFetch(`/payments-calendar?${qs.toString()}`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch payments calendar');
  const raw: PaymentsCalendarRaw = await res.json();
  return {
    year: raw.year,
    month: raw.month,
    currency: raw.currency,
    items: raw.items.map(mapItem),
  };
}
