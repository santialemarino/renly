import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface SkippedInvestmentRaw {
  investment_id: number;
  name: string;
  base_currency: string;
}

interface PortfolioMetricsRaw {
  total_value: string;
  total_invested: string;
  absolute_gain: string;
  total_return_pct: string | null;
  twr: string | null;
  irr: string | null;
  month_change: string | null;
  month_change_pct: string | null;
  currency: string | null;
  skipped_investments: SkippedInvestmentRaw[];
}

interface EvolutionPointRaw {
  date: string;
  total_value: string;
}

interface PortfolioEvolutionRaw {
  points: EvolutionPointRaw[];
  currency: string | null;
  skipped_investments: SkippedInvestmentRaw[];
}

interface AllocationItemRaw {
  category: string;
  value: string;
  percentage: string;
}

interface AllocationResponseRaw {
  items: AllocationItemRaw[];
  total_value: string;
  skipped_investments: SkippedInvestmentRaw[];
}

interface GroupAllocationItemRaw {
  group_name: string;
  value: string;
  percentage: string;
}

interface GroupAllocationResponseRaw {
  items: GroupAllocationItemRaw[];
  total_value: string;
  skipped_investments: SkippedInvestmentRaw[];
}

interface InvestmentSummaryItemRaw {
  investment_id: number;
  name: string;
  category: string;
  current_value: string | null;
  invested_capital: string;
  absolute_gain: string | null;
  month_change_pct: string | null;
  currency: string;
}

interface InvestmentsSummaryResponseRaw {
  items: InvestmentSummaryItemRaw[];
  skipped_investments: SkippedInvestmentRaw[];
}

interface PeriodReturnItemRaw {
  date: string;
  value: string;
  return_pct: string | null;
}

interface InvestmentMetricsRaw {
  investment_id: number;
  name: string;
  category: string;
  base_currency: string;
  current_value: string | null;
  invested_capital: string;
  absolute_gain: string | null;
  simple_return: string | null;
  twr: string | null;
  irr: string | null;
  period_returns: PeriodReturnItemRaw[];
  currency: string;
}

// --- Frontend types (camelCase) ---

export interface SkippedInvestment {
  investmentId: number;
  name: string;
  baseCurrency: string;
}

export interface PortfolioMetrics {
  totalValue: number;
  totalInvested: number;
  absoluteGain: number;
  totalReturnPct: number | null;
  twr: number | null;
  irr: number | null;
  monthChange: number | null;
  monthChangePct: number | null;
  currency: string | null;
  skippedInvestments: SkippedInvestment[];
}

export interface EvolutionPoint {
  date: string;
  totalValue: number;
}

export interface PortfolioEvolution {
  points: EvolutionPoint[];
  currency: string | null;
  skippedInvestments: SkippedInvestment[];
}

export interface AllocationItem {
  category: string;
  value: number;
  percentage: number;
}

export interface AllocationResponse {
  items: AllocationItem[];
  totalValue: number;
  skippedInvestments: SkippedInvestment[];
}

export interface GroupAllocationItem {
  groupName: string;
  value: number;
  percentage: number;
}

export interface GroupAllocationResponse {
  items: GroupAllocationItem[];
  totalValue: number;
  skippedInvestments: SkippedInvestment[];
}

export interface InvestmentSummaryItem {
  investmentId: number;
  name: string;
  category: string;
  currentValue: number | null;
  investedCapital: number;
  absoluteGain: number | null;
  monthChangePct: number | null;
  currency: string;
}

export interface InvestmentsSummaryResponse {
  items: InvestmentSummaryItem[];
  skippedInvestments: SkippedInvestment[];
}

export interface PeriodReturnItem {
  date: string;
  value: number;
  returnPct: number | null;
}

export interface InvestmentMetrics {
  investmentId: number;
  name: string;
  category: string;
  baseCurrency: string;
  currentValue: number | null;
  investedCapital: number;
  absoluteGain: number | null;
  simpleReturn: number | null;
  twr: number | null;
  irr: number | null;
  periodReturns: PeriodReturnItem[];
  currency: string;
}

// --- Mappers ---

function mapSkipped(raw: SkippedInvestmentRaw[]): SkippedInvestment[] {
  return raw.map((s) => ({
    investmentId: s.investment_id,
    name: s.name,
    baseCurrency: s.base_currency,
  }));
}

function mapPortfolioMetrics(raw: PortfolioMetricsRaw): PortfolioMetrics {
  return {
    totalValue: Number(raw.total_value),
    totalInvested: Number(raw.total_invested),
    absoluteGain: Number(raw.absolute_gain),
    totalReturnPct: raw.total_return_pct !== null ? Number(raw.total_return_pct) : null,
    twr: raw.twr !== null ? Number(raw.twr) : null,
    irr: raw.irr !== null ? Number(raw.irr) : null,
    monthChange: raw.month_change !== null ? Number(raw.month_change) : null,
    monthChangePct: raw.month_change_pct !== null ? Number(raw.month_change_pct) : null,
    currency: raw.currency,
    skippedInvestments: mapSkipped(raw.skipped_investments),
  };
}

function mapEvolutionPoint(raw: EvolutionPointRaw): EvolutionPoint {
  return {
    date: raw.date,
    totalValue: Number(raw.total_value),
  };
}

function mapAllocationItem(raw: AllocationItemRaw): AllocationItem {
  return {
    category: raw.category,
    value: Number(raw.value),
    percentage: Number(raw.percentage),
  };
}

function mapGroupAllocationItem(raw: GroupAllocationItemRaw): GroupAllocationItem {
  return {
    groupName: raw.group_name,
    value: Number(raw.value),
    percentage: Number(raw.percentage),
  };
}

function mapInvestmentSummaryItem(raw: InvestmentSummaryItemRaw): InvestmentSummaryItem {
  return {
    investmentId: raw.investment_id,
    name: raw.name,
    category: raw.category,
    currentValue: raw.current_value !== null ? Number(raw.current_value) : null,
    investedCapital: Number(raw.invested_capital),
    absoluteGain: raw.absolute_gain !== null ? Number(raw.absolute_gain) : null,
    monthChangePct: raw.month_change_pct !== null ? Number(raw.month_change_pct) : null,
    currency: raw.currency,
  };
}

function mapInvestmentMetrics(raw: InvestmentMetricsRaw): InvestmentMetrics {
  return {
    investmentId: raw.investment_id,
    name: raw.name,
    category: raw.category,
    baseCurrency: raw.base_currency,
    currentValue: raw.current_value !== null ? Number(raw.current_value) : null,
    investedCapital: Number(raw.invested_capital),
    absoluteGain: raw.absolute_gain !== null ? Number(raw.absolute_gain) : null,
    simpleReturn: raw.simple_return !== null ? Number(raw.simple_return) : null,
    twr: raw.twr !== null ? Number(raw.twr) : null,
    irr: raw.irr !== null ? Number(raw.irr) : null,
    periodReturns: raw.period_returns.map((pr) => ({
      date: pr.date,
      value: Number(pr.value),
      returnPct: pr.return_pct !== null ? Number(pr.return_pct) : null,
    })),
    currency: raw.currency,
  };
}

// --- Shared filter params ---

export interface MetricsFilterParams {
  currency?: string;
  investmentIds?: number[];
  groupIds?: number[];
  category?: string;
  search?: string;
  startDate?: string;
  endDate?: string;
}

function buildFilterQuery(params: MetricsFilterParams): string {
  const qs = new URLSearchParams();
  if (params.currency) qs.append('currency', params.currency);
  if (params.investmentIds) {
    params.investmentIds.forEach((id) => qs.append('investment_ids', String(id)));
  }
  if (params.groupIds) {
    params.groupIds.forEach((id) => qs.append('group_ids', String(id)));
  }
  if (params.category) qs.append('category', params.category);
  if (params.search) qs.append('search', params.search);
  if (params.startDate) qs.append('start_date', params.startDate);
  if (params.endDate) qs.append('end_date', params.endDate);
  return qs.toString();
}

// --- API functions ---

export async function getPortfolioMetrics(
  params: MetricsFilterParams = {},
): Promise<PortfolioMetrics> {
  const query = buildFilterQuery(params);
  const url = `/metrics/portfolio${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch portfolio metrics');

  const raw: PortfolioMetricsRaw = await res.json();
  return mapPortfolioMetrics(raw);
}

export async function getPortfolioEvolution(
  params: MetricsFilterParams = {},
): Promise<PortfolioEvolution> {
  const query = buildFilterQuery(params);
  const url = `/metrics/portfolio/evolution${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch portfolio evolution');

  const raw: PortfolioEvolutionRaw = await res.json();
  return {
    points: raw.points.map(mapEvolutionPoint),
    currency: raw.currency,
    skippedInvestments: mapSkipped(raw.skipped_investments),
  };
}

export async function getAllocation(params: MetricsFilterParams = {}): Promise<AllocationResponse> {
  const query = buildFilterQuery(params);
  const url = `/metrics/allocation${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch allocation');

  const raw: AllocationResponseRaw = await res.json();
  return {
    items: raw.items.map(mapAllocationItem),
    totalValue: Number(raw.total_value),
    skippedInvestments: mapSkipped(raw.skipped_investments),
  };
}

export async function getAllocationByGroup(
  params: MetricsFilterParams = {},
): Promise<GroupAllocationResponse> {
  const query = buildFilterQuery(params);
  const url = `/metrics/allocation/by-group${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch group allocation');

  const raw: GroupAllocationResponseRaw = await res.json();
  return {
    items: raw.items.map(mapGroupAllocationItem),
    totalValue: Number(raw.total_value),
    skippedInvestments: mapSkipped(raw.skipped_investments),
  };
}

export async function getInvestmentsSummary(
  params: MetricsFilterParams = {},
): Promise<InvestmentsSummaryResponse> {
  const query = buildFilterQuery(params);
  const url = `/metrics/investments/summary${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch investments summary');

  const raw: InvestmentsSummaryResponseRaw = await res.json();
  return {
    items: raw.items.map(mapInvestmentSummaryItem),
    skippedInvestments: mapSkipped(raw.skipped_investments),
  };
}

export async function getInvestmentMetrics(
  investmentId: number,
  currency?: string,
): Promise<InvestmentMetrics> {
  const qs = new URLSearchParams();
  if (currency) qs.append('currency', currency);

  const query = qs.toString();
  const url = `/metrics/investment/${investmentId}${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch investment metrics');

  const raw: InvestmentMetricsRaw = await res.json();
  return mapInvestmentMetrics(raw);
}
