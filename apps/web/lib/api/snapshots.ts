import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SnapshotGridTransactionRaw {
  id: number;
  amount: string;
  original_amount: string;
  quantity: string | null;
  type: string;
}

interface SnapshotGridCellRaw {
  date: string;
  value: string;
  original_value: string;
  quantity: string | null;
  source: string;
  period_return_pct: string | null;
  has_transaction: boolean;
  transaction: SnapshotGridTransactionRaw | null;
}

interface SnapshotGridRowRaw {
  investment_id: number;
  name: string;
  category: string;
  base_currency: string;
  ticker: string | null;
  cedear_ratio: string | null;
  cells: SnapshotGridCellRaw[];
}

interface SnapshotGridResponseRaw {
  rows: SnapshotGridRowRaw[];
  months: string[];
}

// --- Frontend types (camelCase) ---

export interface SnapshotGridTransaction {
  id: number;
  amount: number;
  originalAmount: number;
  quantity: number | null;
  type: string;
}

export interface SnapshotGridCell {
  date: string;
  value: number;
  originalValue: number;
  quantity: number | null;
  source: string;
  periodReturnPct: number | null;
  hasTransaction: boolean;
  transaction: SnapshotGridTransaction | null;
}

export interface SnapshotGridRow {
  investmentId: number;
  name: string;
  category: string;
  baseCurrency: string;
  ticker: string | null;
  cedearRatio: number | null;
  cells: SnapshotGridCell[];
}

export interface SnapshotGridResponse {
  rows: SnapshotGridRow[];
  months: string[];
}

export interface GetSnapshotGridParams {
  search?: string;
  groupIds?: number[];
  category?: string;
  currency?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

// --- Mappers ---

function mapCell(raw: SnapshotGridCellRaw): SnapshotGridCell {
  return {
    date: raw.date,
    value: Number(raw.value),
    originalValue: Number(raw.original_value),
    quantity: raw.quantity !== null ? Number(raw.quantity) : null,
    source: raw.source,
    periodReturnPct: raw.period_return_pct !== null ? Number(raw.period_return_pct) : null,
    hasTransaction: raw.has_transaction,
    transaction: raw.transaction
      ? {
          id: raw.transaction.id,
          amount: Number(raw.transaction.amount),
          originalAmount: Number(raw.transaction.original_amount),
          quantity: raw.transaction.quantity !== null ? Number(raw.transaction.quantity) : null,
          type: raw.transaction.type,
        }
      : null,
  };
}

function mapRow(raw: SnapshotGridRowRaw): SnapshotGridRow {
  return {
    investmentId: raw.investment_id,
    name: raw.name,
    category: raw.category,
    baseCurrency: raw.base_currency,
    ticker: raw.ticker,
    cedearRatio: raw.cedear_ratio !== null ? Number(raw.cedear_ratio) : null,
    cells: raw.cells.map(mapCell),
  };
}

// --- API functions ---

export async function getSnapshotGrid(
  params?: GetSnapshotGridParams,
): Promise<SnapshotGridResponse> {
  const qs = new URLSearchParams();

  if (params?.search) qs.append('search', params.search);
  if (params?.groupIds) {
    params.groupIds.forEach((id) => qs.append('group_ids', String(id)));
  }
  if (params?.category) qs.append('category', params.category);
  if (params?.currency) qs.append('currency', params.currency);
  if (params?.sortBy) qs.append('sort_by', params.sortBy);
  if (params?.sortOrder) qs.append('sort_order', params.sortOrder);

  const query = qs.toString();
  const url = `/snapshots/grid${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch snapshot grid');

  const raw: SnapshotGridResponseRaw = await res.json();
  return {
    rows: raw.rows.map(mapRow),
    months: raw.months,
  };
}
