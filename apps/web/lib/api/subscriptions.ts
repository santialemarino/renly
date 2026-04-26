import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SubscriptionRaw {
  id: number;
  name: string;
  amount: string;
  currency: string;
  converted_amount: string | null;
  billing_cycle: string;
  next_billing_date: string;
  payment_method: string | null;
  credit_card_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface Subscription {
  id: number;
  name: string;
  amount: string;
  currency: string;
  convertedAmount: string | null;
  billingCycle: string;
  nextBillingDate: string;
  paymentMethod: string | null;
  creditCardId: number | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapSubscription(raw: SubscriptionRaw): Subscription {
  return {
    id: raw.id,
    name: raw.name,
    amount: raw.amount,
    currency: raw.currency,
    convertedAmount: raw.converted_amount,
    billingCycle: raw.billing_cycle,
    nextBillingDate: raw.next_billing_date,
    paymentMethod: raw.payment_method,
    creditCardId: raw.credit_card_id,
    isActive: raw.is_active,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type SubscriptionSortField =
  | 'name'
  | 'amount'
  | 'currency'
  | 'billing_cycle'
  | 'next_billing_date';
export type SortOrder = 'asc' | 'desc';

export interface GetSubscriptionsParams {
  search?: string;
  sortBy?: SubscriptionSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
  currency?: string;
}

export async function getSubscriptions(
  params: GetSubscriptionsParams = {},
): Promise<Subscription[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');
  if (params.currency) qs.set('currency', params.currency);

  const endpoint = qs.toString() ? `/subscriptions?${qs.toString()}` : '/subscriptions';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch subscriptions');
  const raw: SubscriptionRaw[] = await res.json();
  return raw.map(mapSubscription);
}
