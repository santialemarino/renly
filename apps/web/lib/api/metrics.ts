import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface PortfolioMetricsRaw {
  total_value: string;
  total_invested: string;
  absolute_gain: string;
  total_return_pct: string | null;
  month_change: string | null;
  month_change_pct: string | null;
  currency: string | null;
}

interface EvolutionPointRaw {
  date: string;
  total_value: string;
}

interface PortfolioEvolutionRaw {
  points: EvolutionPointRaw[];
  currency: string | null;
}

interface AllocationItemRaw {
  category: string;
  value: string;
  percentage: string;
}

interface AllocationResponseRaw {
  items: AllocationItemRaw[];
  total_value: string;
}

interface GroupAllocationItemRaw {
  group_name: string;
  value: string;
  percentage: string;
}

interface GroupAllocationResponseRaw {
  items: GroupAllocationItemRaw[];
  total_value: string;
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
}

// --- Frontend types (camelCase) ---

export interface PortfolioMetrics {
  totalValue: number;
  totalInvested: number;
  absoluteGain: number;
  totalReturnPct: number | null;
  monthChange: number | null;
  monthChangePct: number | null;
  currency: string | null;
}

export interface EvolutionPoint {
  date: string;
  totalValue: number;
}

export interface PortfolioEvolution {
  points: EvolutionPoint[];
  currency: string | null;
}

export interface AllocationItem {
  category: string;
  value: number;
  percentage: number;
}

export interface AllocationResponse {
  items: AllocationItem[];
  totalValue: number;
}

export interface GroupAllocationItem {
  groupName: string;
  value: number;
  percentage: number;
}

export interface GroupAllocationResponse {
  items: GroupAllocationItem[];
  totalValue: number;
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
}

// --- Mappers ---

function mapPortfolioMetrics(raw: PortfolioMetricsRaw): PortfolioMetrics {
  return {
    totalValue: Number(raw.total_value),
    totalInvested: Number(raw.total_invested),
    absoluteGain: Number(raw.absolute_gain),
    totalReturnPct: raw.total_return_pct !== null ? Number(raw.total_return_pct) : null,
    monthChange: raw.month_change !== null ? Number(raw.month_change) : null,
    monthChangePct: raw.month_change_pct !== null ? Number(raw.month_change_pct) : null,
    currency: raw.currency,
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

// --- API functions ---

export async function getPortfolioMetrics(currency?: string): Promise<PortfolioMetrics> {
  const qs = new URLSearchParams();
  if (currency) qs.append('currency', currency);

  const query = qs.toString();
  const url = `/metrics/portfolio${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch portfolio metrics');

  const raw: PortfolioMetricsRaw = await res.json();
  return mapPortfolioMetrics(raw);
}

export async function getPortfolioEvolution(currency?: string): Promise<PortfolioEvolution> {
  const qs = new URLSearchParams();
  if (currency) qs.append('currency', currency);

  const query = qs.toString();
  const url = `/metrics/portfolio/evolution${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch portfolio evolution');

  const raw: PortfolioEvolutionRaw = await res.json();
  return {
    points: raw.points.map(mapEvolutionPoint),
    currency: raw.currency,
  };
}

export async function getAllocation(currency?: string): Promise<AllocationResponse> {
  const qs = new URLSearchParams();
  if (currency) qs.append('currency', currency);

  const query = qs.toString();
  const url = `/metrics/allocation${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch allocation');

  const raw: AllocationResponseRaw = await res.json();
  return {
    items: raw.items.map(mapAllocationItem),
    totalValue: Number(raw.total_value),
  };
}

export async function getAllocationByGroup(currency?: string): Promise<GroupAllocationResponse> {
  const qs = new URLSearchParams();
  if (currency) qs.append('currency', currency);

  const query = qs.toString();
  const url = `/metrics/allocation/by-group${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch group allocation');

  const raw: GroupAllocationResponseRaw = await res.json();
  return {
    items: raw.items.map(mapGroupAllocationItem),
    totalValue: Number(raw.total_value),
  };
}

export async function getInvestmentsSummary(
  currency?: string,
): Promise<InvestmentsSummaryResponse> {
  const qs = new URLSearchParams();
  if (currency) qs.append('currency', currency);

  const query = qs.toString();
  const url = `/metrics/investments/summary${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch investments summary');

  const raw: InvestmentsSummaryResponseRaw = await res.json();
  return {
    items: raw.items.map(mapInvestmentSummaryItem),
  };
}
