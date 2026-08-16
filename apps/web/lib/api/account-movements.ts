// Server-only types + mappers for the per-account ledger: every movement that reaches one account,
// newest first. `amount` is signed in the account's currency, and `balanceAfter` is the balance
// immediately after the movement — populated only on the unfiltered view (see the API service for
// why a filtered ledger withholds it).

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { MovementKind, MovementSource } from '@/lib/constants/accounts';

// --- Raw types (API JSON shape, snake_case) ---

interface AccountMovementRaw {
  source: string;
  source_id: number;
  kind: string;
  date: string;
  amount: string;
  balance_after: string | null;
  category: string | null;
  counterparty: string | null;
  counterparty_amount: string | null;
  counterparty_currency: string | null;
  notes: string | null;
}

interface AccountMovementListRaw {
  items: AccountMovementRaw[];
  total: number;
  page: number;
  page_size: number;
  currency: string;
}

// --- Frontend types (camelCase) ---

export interface AccountMovement {
  source: MovementSource;
  sourceId: number;
  kind: MovementKind;
  date: string;
  amount: string;
  balanceAfter: string | null;
  category: string | null;
  counterparty: string | null;
  counterpartyAmount: string | null;
  counterpartyCurrency: string | null;
  notes: string | null;
}

export interface AccountMovementList {
  items: AccountMovement[];
  total: number;
  page: number;
  pageSize: number;
  currency: string;
}

// --- Mappers ---

function mapAccountMovement(raw: AccountMovementRaw): AccountMovement {
  return {
    source: raw.source as MovementSource,
    sourceId: raw.source_id,
    kind: raw.kind as MovementKind,
    date: raw.date,
    amount: raw.amount,
    balanceAfter: raw.balance_after,
    category: raw.category,
    counterparty: raw.counterparty,
    counterpartyAmount: raw.counterparty_amount,
    counterpartyCurrency: raw.counterparty_currency,
    notes: raw.notes,
  };
}

function mapAccountMovementList(raw: AccountMovementListRaw): AccountMovementList {
  return {
    items: raw.items.map(mapAccountMovement),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
    currency: raw.currency,
  };
}

// --- API functions ---

export interface GetAccountMovementsParams {
  kind?: MovementKind;
  page?: number;
  pageSize?: number;
}

export async function getAccountMovements(
  accountId: number,
  params: GetAccountMovementsParams = {},
): Promise<AccountMovementList> {
  const qs = new URLSearchParams();
  if (params.kind) qs.set('kind', params.kind);
  if (params.page && params.page > 1) qs.set('page', String(params.page));
  if (params.pageSize) qs.set('page_size', String(params.pageSize));

  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  const res = await authenticatedFetch(`/accounts/${accountId}/movements${suffix}`, {
    method: 'GET',
  });
  if (!res.ok) throw new Error('Failed to fetch account movements');
  const raw: AccountMovementListRaw = await res.json();
  return mapAccountMovementList(raw);
}
