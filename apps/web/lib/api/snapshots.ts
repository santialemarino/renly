import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SnapshotGridTransactionRaw {
  id: number;
  amount: string;
  type: string;
}

interface SnapshotGridCellRaw {
  date: string;
  value: string;
  period_return_pct: string | null;
  has_transaction: boolean;
  transaction: SnapshotGridTransactionRaw | null;
}

interface SnapshotGridRowRaw {
  investment_id: number;
  name: string;
  category: string;
  base_currency: string;
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
  type: string;
}

export interface SnapshotGridCell {
  date: string;
  value: number;
  periodReturnPct: number | null;
  hasTransaction: boolean;
  transaction: SnapshotGridTransaction | null;
}

export interface SnapshotGridRow {
  investmentId: number;
  name: string;
  category: string;
  baseCurrency: string;
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
}

// --- Mappers ---

function mapCell(raw: SnapshotGridCellRaw): SnapshotGridCell {
  return {
    date: raw.date,
    value: Number(raw.value),
    periodReturnPct: raw.period_return_pct !== null ? Number(raw.period_return_pct) : null,
    hasTransaction: raw.has_transaction,
    transaction: raw.transaction
      ? {
          id: raw.transaction.id,
          amount: Number(raw.transaction.amount),
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
    for (const id of params.groupIds) qs.append('group_ids', String(id));
  }
  if (params?.category) qs.append('category', params.category);

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
