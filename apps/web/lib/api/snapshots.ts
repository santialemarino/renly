import 'server-only';

import {
  mapListSection,
  type ListScope,
  type ListSection,
  type ListSectionRaw,
} from '@/lib/api/types';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SnapshotGridTransactionRaw {
  id: number;
  amount: string;
  original_amount: string;
  quantity: string | null;
  type: string;
}

interface SkippedInvestmentRaw {
  investment_id: number;
  name: string;
  base_currency: string;
}

interface SnapshotGridCellRaw {
  date: string;
  column: string;
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
  scope: string;
  pot_id: number | null;
  cadence: string | null;
  is_overdue: boolean;
  cells: SnapshotGridCellRaw[];
}

interface SnapshotGridResponseRaw {
  rows: SnapshotGridRowRaw[];
  columns: string[];
  interval: string;
  sections: ListSectionRaw[];
  skipped_investments: SkippedInvestmentRaw[];
}

// --- Frontend types (camelCase) ---

export interface SnapshotGridTransaction {
  id: number;
  amount: number;
  originalAmount: number;
  quantity: number | null;
  type: string;
}

export interface SkippedInvestment {
  investmentId: number;
  name: string;
  baseCurrency: string;
}

export interface SnapshotGridCell {
  date: string;
  // The grid column this snapshot falls in — its month's last day, or its week's Sunday. Resolved on
  // the server so ONE rule decides which week a Wednesday belongs to: the pot page's value series is
  // measured on the same one, and two copies of it would drift by a week.
  column: string;
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
  scope: 'private' | 'shared';
  potId: number | null;
  // The owning pot's re-valuation cadence, and whether THIS holding's latest snapshot is behind it
  // (§8.2's freshness indicator). Null / false on a private row, which declares no rhythm to be late
  // against. Per row rather than per section because lateness is a fact about one holding.
  cadence: SnapshotCadence | null;
  isOverdue: boolean;
  cells: SnapshotGridCell[];
}

export type SnapshotGridInterval = 'monthly' | 'weekly';
export type SnapshotCadence = 'ad_hoc' | 'monthly' | 'weekly';

export interface SnapshotGridResponse {
  rows: SnapshotGridRow[];
  // One period end per column, ascending and gapless, from the oldest recorded snapshot's period
  // through the newest's — capped at the most recent, which is what makes weekly usable over years.
  columns: string[];
  interval: SnapshotGridInterval;
  sections: ListSection[];
  // Investments left out because their currency has no stored rate to the display currency. The API
  // has computed these since Phase 3 and this grid never rendered them, so such a holding simply
  // vanished from a page claiming to show everything.
  skippedInvestments: SkippedInvestment[];
}

export interface GetSnapshotGridParams {
  // Both default to the narrowest answer on the API: 'private' (the investor dashboard reads the same
  // repository function and stays private by decision) and 'monthly'.
  scope?: ListScope;
  interval?: SnapshotGridInterval;
  search?: string;
  collectionIds?: number[];
  category?: string;
  currency?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

// --- Mappers ---

function mapCell(raw: SnapshotGridCellRaw): SnapshotGridCell {
  return {
    date: raw.date,
    column: raw.column,
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
    scope: raw.scope === 'shared' ? 'shared' : 'private',
    potId: raw.pot_id,
    cadence: raw.cadence as SnapshotCadence | null,
    isOverdue: raw.is_overdue,
    cells: raw.cells.map(mapCell),
  };
}

// --- API functions ---

export async function getSnapshotGrid(
  params?: GetSnapshotGridParams,
): Promise<SnapshotGridResponse> {
  const qs = new URLSearchParams();

  if (params?.scope) qs.append('scope', params.scope);
  if (params?.interval) qs.append('interval', params.interval);
  if (params?.search) qs.append('search', params.search);
  if (params?.collectionIds) {
    params.collectionIds.forEach((id) => qs.append('collection_ids', String(id)));
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
    columns: raw.columns,
    interval: raw.interval === 'weekly' ? 'weekly' : 'monthly',
    sections: raw.sections.map(mapListSection),
    skippedInvestments: raw.skipped_investments.map((skipped) => ({
      investmentId: skipped.investment_id,
      name: skipped.name,
      baseCurrency: skipped.base_currency,
    })),
  };
}
