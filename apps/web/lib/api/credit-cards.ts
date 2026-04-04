import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface CreditCardRaw {
  id: number;
  name: string;
  closing_day: number;
  due_day: number;
  currency: string;
  is_active: boolean;
  balance: string;
  created_at: string;
  updated_at: string;
}

interface CardSettlementRaw {
  id: number;
  credit_card_id: number;
  date: string;
  amount: string;
  currency: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface CreditCard {
  id: number;
  name: string;
  closingDay: number;
  dueDay: number;
  currency: string;
  isActive: boolean;
  balance: string;
  createdAt: string;
  updatedAt: string;
}

export interface CardSettlement {
  id: number;
  creditCardId: number;
  date: string;
  amount: string;
  currency: string;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

function mapCreditCard(raw: CreditCardRaw): CreditCard {
  return {
    id: raw.id,
    name: raw.name,
    closingDay: raw.closing_day,
    dueDay: raw.due_day,
    currency: raw.currency,
    isActive: raw.is_active,
    balance: raw.balance,
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
    notes: raw.notes,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

// --- API functions ---

export type CreditCardSortField = 'name' | 'closing_day' | 'due_day' | 'currency';
export type SortOrder = 'asc' | 'desc';

export interface GetCreditCardsParams {
  search?: string;
  sortBy?: CreditCardSortField;
  sortOrder?: SortOrder;
}

export async function getCreditCards(params: GetCreditCardsParams = {}): Promise<CreditCard[]> {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.sortBy) qs.set('sort_by', params.sortBy);
  if (params.sortOrder) qs.set('sort_order', params.sortOrder);

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
