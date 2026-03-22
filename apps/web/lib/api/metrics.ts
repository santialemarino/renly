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
