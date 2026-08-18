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
  default_account_id: number | null;
  balances: CardBucketBalanceRaw[];
  has_expenses: boolean;
  created_at: string;
  updated_at: string;
}

// Exported so the colocated actions file maps the same wire shape instead of re-declaring it:
// the settlements list is fetched from a client component, which can't import this server-only module
// at runtime, so `fetchSettlements` lives in the actions file and reuses these.
export interface CardSettlementRaw {
  id: number;
  credit_card_id: number;
  date: string;
  amount: string;
  currency: string;
  account_id: number | null;
  account_name: string | null;
  account_currency: string | null;
  account_amount: string | null;
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
  defaultAccountId: number | null;
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
  // Denormalized by the API so an archived funding account still renders by name — and so a row can say
  // which currency it was paid in without a second fetch that can fail.
  accountName: string | null;
  accountCurrency: string | null;
  /*
   * What actually left the funding account, in that account's currency. Null whenever no conversion
   * happened, so the cash leg reads `accountAmount ?? amount` and the pair is shown only when the two
   * genuinely differ. `amount`/`currency` above stay the CARD leg — what the payment cleared off the
   * bucket — so a US$100 bill paid with $130,000 records both and derives no rate from either.
   */
  accountAmount: string | null;
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
    defaultAccountId: raw.default_account_id,
    balances: raw.balances.map((b) => ({ currency: b.currency, balance: b.balance })),
    hasExpenses: raw.has_expenses,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

export function mapSettlement(raw: CardSettlementRaw): CardSettlement {
  return {
    id: raw.id,
    creditCardId: raw.credit_card_id,
    date: raw.date,
    amount: raw.amount,
    currency: raw.currency,
    accountId: raw.account_id,
    accountName: raw.account_name,
    accountCurrency: raw.account_currency,
    accountAmount: raw.account_amount,
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
