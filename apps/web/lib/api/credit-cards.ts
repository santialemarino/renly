import 'server-only';

import type { SortOrder } from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface CardBucketBalanceRaw {
  currency: string;
  balance: string;
}

interface CreditCardRaw {
  id: number;
  name: string;
  closing_day: number;
  due_day: number;
  currency: string;
  is_active: boolean;
  monthly_payment: string | null;
  balances: CardBucketBalanceRaw[];
  has_expenses: boolean;
  created_at: string;
  updated_at: string;
}

interface CardSettlementRaw {
  id: number;
  credit_card_id: number;
  date: string;
  amount: string;
  currency: string;
  account_id: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface CardBucketBalance {
  currency: string;
  balance: string;
}

export interface CreditCard {
  id: number;
  name: string;
  closingDay: number;
  dueDay: number;
  currency: string;
  isActive: boolean;
  monthlyPayment: number | null;
  balances: CardBucketBalance[];
  hasExpenses: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CardSettlement {
  id: number;
  creditCardId: number;
  date: string;
  amount: string;
  currency: string;
  accountId: number | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

export function mapCreditCard(raw: CreditCardRaw): CreditCard {
  return {
    id: raw.id,
    name: raw.name,
    closingDay: raw.closing_day,
    dueDay: raw.due_day,
    currency: raw.currency,
    isActive: raw.is_active,
    monthlyPayment: raw.monthly_payment !== null ? Number(raw.monthly_payment) : null,
    balances: raw.balances.map((b) => ({ currency: b.currency, balance: b.balance })),
    hasExpenses: raw.has_expenses,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function mapSettlement(raw: CardSettlementRaw): CardSettlement {
  return {
    id: raw.id,
    creditCardId: raw.credit_card_id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    accountId: raw.account_id,
    notes: raw.notes,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type CreditCardSortField = 'name' | 'closing_day' | 'due_day' | 'currency';

export interface GetCreditCardsParams {
  search?: string;
  sortBy?: CreditCardSortField;
  sortOrder?: SortOrder;
  showArchived?: boolean;
}

export async function getCreditCards(params: GetCreditCardsParams = {}): Promise<CreditCard[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);
  if (params.showArchived) qs.set('show_archived', 'true');

  const endpoint = qs.toString() ? `/credit-cards?${qs.toString()}` : '/credit-cards';
  const res = await authenticatedFetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch credit cards');
  const raw: CreditCardRaw[] = await res.json();
  return raw.map(mapCreditCard);
}

export async function getSettlements(cardId: number): Promise<CardSettlement[]> {
  const res = await authenticatedFetch(`/credit-cards/${cardId}/settlements`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch settlements');
  const raw: CardSettlementRaw[] = await res.json();
  return raw.map(mapSettlement);
}
