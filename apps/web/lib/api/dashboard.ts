import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface UndividedPotRaw {
  pot_id: number;
  name: string | null;
  group_id: number;
  group_name: string;
}

interface DashboardOverviewRaw {
  net_worth: string;
  private_net_worth: string;
  shared_net_worth: string;
  shared_pot_value: string;
  shared_receivable: string;
  shared_payable: string;
  has_shared: boolean;
  undivided_pots: UndividedPotRaw[];
  cash_total: string;
  net_worth_change: string | null;
  net_worth_change_pct: string | null;
  investment_total: string;
  investment_gain: string;
  investment_gain_pct: string | null;
  investment_month_change: string | null;
  investment_month_change_pct: string | null;
  credit_card_balance: string;
  total_income: string;
  total_expenses: string;
  savings_rate: string | null;
  income_expense_ratio: string | null;
  currency: string | null;
  has_holdings: boolean;
  skipped_currencies: string[];
}

interface NetWorthEvolutionPointRaw {
  date: string;
  investment_value: string;
  cash_balance: string;
  card_balance: string;
  shared_value: string;
  private_net_worth: string;
  net_worth: string;
}

interface DashboardEvolutionRaw {
  points: NetWorthEvolutionPointRaw[];
  currency: string | null;
  skipped_currencies: string[];
}

interface CompositionItemRaw {
  label: string;
  value: string;
  percentage: string;
}

interface DashboardCompositionRaw {
  items: CompositionItemRaw[];
  total_assets: string;
  total_liabilities: string;
  currency: string | null;
  skipped_currencies: string[];
}

interface SkippedLiquidityEntityRaw {
  type: 'subscription' | 'installment' | 'obligation' | 'credit_card';
  name: string;
  currency: string;
}

interface DashboardLiquidityRaw {
  ratio: string | null;
  state: 'healthy' | 'caution' | 'at_risk' | 'unknown';
  fixed_monthly_commitments: string;
  monthly_income: string;
  threshold: number;
  income_window_days: number;
  actual_window_days: number;
  currency: string | null;
  skipped_entities: SkippedLiquidityEntityRaw[];
}

// --- Frontend types (camelCase) ---

// A pot holding value that no ownership baseline divides yet, so it contributes exactly nothing to
// anybody's net worth. `name` is null for a group's default pot — the renderer supplies the fallback.
export interface UndividedPot {
  potId: number;
  name: string | null;
  groupId: number;
  // Never null: the copy reads "{pot} in {group}", and the API drops a pot whose group it cannot name
  // rather than emitting a sentence with a hole in it.
  groupName: string;
}

export interface DashboardOverview {
  netWorth: number;
  // The 'Yours' half of the headline: private investments plus private cash minus card debt.
  privateNetWorth: number;
  // The 'Shared' half: your share of every visible pot, plus receivables, less payables.
  sharedNetWorth: number;
  sharedPotValue: number;
  sharedReceivable: number;
  sharedPayable: number;
  // Existence, not value — a household whose balances net to zero still gets the breakdown.
  hasShared: boolean;
  undividedPots: UndividedPot[];
  cashTotal: number;
  netWorthChange: number | null;
  netWorthChangePct: number | null;
  investmentTotal: number;
  investmentGain: number;
  investmentGainPct: number | null;
  investmentMonthChange: number | null;
  investmentMonthChangePct: number | null;
  creditCardBalance: number;
  totalIncome: number;
  totalExpenses: number;
  savingsRate: number | null;
  incomeExpenseRatio: number | null;
  currency: string | null;
  // Whether the user holds any investment, account, or card — true even when the figures net to zero.
  hasHoldings: boolean;
  // Original-currency codes the totals had to exclude because no exchange rate was stored.
  skippedCurrencies: string[];
}

export interface NetWorthEvolutionPoint {
  date: string;
  investmentValue: number;
  cashBalance: number;
  cardBalance: number;
  sharedValue: number;
  privateNetWorth: number;
  netWorth: number;
}

export interface DashboardEvolution {
  points: NetWorthEvolutionPoint[];
  currency: string | null;
  skippedCurrencies: string[];
}

export interface CompositionItem {
  label: string;
  value: number;
  percentage: number;
}

export interface DashboardComposition {
  items: CompositionItem[];
  totalAssets: number;
  totalLiabilities: number;
  currency: string | null;
  skippedCurrencies: string[];
}

export type LiquidityState = 'healthy' | 'caution' | 'at_risk' | 'unknown';

export interface SkippedLiquidityEntity {
  type: 'subscription' | 'installment' | 'obligation' | 'credit_card';
  name: string;
  currency: string;
}

export interface DashboardLiquidity {
  ratio: number | null;
  state: LiquidityState;
  fixedMonthlyCommitments: number;
  monthlyIncome: number;
  threshold: number;
  incomeWindowDays: number;
  actualWindowDays: number;
  currency: string | null;
  skippedEntities: SkippedLiquidityEntity[];
}

// --- Mappers ---

function mapOverview(raw: DashboardOverviewRaw): DashboardOverview {
  return {
    netWorth: Number(raw.net_worth),
    privateNetWorth: Number(raw.private_net_worth),
    sharedNetWorth: Number(raw.shared_net_worth),
    sharedPotValue: Number(raw.shared_pot_value),
    sharedReceivable: Number(raw.shared_receivable),
    sharedPayable: Number(raw.shared_payable),
    hasShared: raw.has_shared === true,
    undividedPots: (raw.undivided_pots ?? []).map((pot) => ({
      potId: pot.pot_id,
      name: pot.name,
      groupId: pot.group_id,
      groupName: pot.group_name,
    })),
    cashTotal: Number(raw.cash_total),
    netWorthChange: raw.net_worth_change !== null ? Number(raw.net_worth_change) : null,
    netWorthChangePct: raw.net_worth_change_pct !== null ? Number(raw.net_worth_change_pct) : null,
    investmentTotal: Number(raw.investment_total),
    investmentGain: Number(raw.investment_gain),
    investmentGainPct: raw.investment_gain_pct !== null ? Number(raw.investment_gain_pct) : null,
    investmentMonthChange:
      raw.investment_month_change !== null ? Number(raw.investment_month_change) : null,
    investmentMonthChangePct:
      raw.investment_month_change_pct !== null ? Number(raw.investment_month_change_pct) : null,
    creditCardBalance: Number(raw.credit_card_balance),
    totalIncome: Number(raw.total_income),
    totalExpenses: Number(raw.total_expenses),
    savingsRate: raw.savings_rate !== null ? Number(raw.savings_rate) : null,
    incomeExpenseRatio: raw.income_expense_ratio !== null ? Number(raw.income_expense_ratio) : null,
    currency: raw.currency,
    hasHoldings: raw.has_holdings === true,
    skippedCurrencies: raw.skipped_currencies ?? [],
  };
}

function mapEvolutionPoint(raw: NetWorthEvolutionPointRaw): NetWorthEvolutionPoint {
  return {
    date: raw.date,
    investmentValue: Number(raw.investment_value),
    cashBalance: Number(raw.cash_balance),
    cardBalance: Number(raw.card_balance),
    sharedValue: Number(raw.shared_value),
    privateNetWorth: Number(raw.private_net_worth),
    netWorth: Number(raw.net_worth),
  };
}

function mapCompositionItem(raw: CompositionItemRaw): CompositionItem {
  return {
    label: raw.label,
    value: Number(raw.value),
    percentage: Number(raw.percentage),
  };
}

function mapLiquidity(raw: DashboardLiquidityRaw): DashboardLiquidity {
  return {
    ratio: raw.ratio !== null ? Number(raw.ratio) : null,
    state: raw.state,
    fixedMonthlyCommitments: Number(raw.fixed_monthly_commitments),
    monthlyIncome: Number(raw.monthly_income),
    threshold: raw.threshold,
    incomeWindowDays: raw.income_window_days,
    actualWindowDays: raw.actual_window_days,
    currency: raw.currency,
    skippedEntities: (raw.skipped_entities ?? []).map((e) => ({
      type: e.type,
      name: e.name,
      currency: e.currency,
    })),
  };
}

// --- Shared filter params ---

export interface DashboardFilterParams {
  currency?: string;
  dateFrom?: string;
  dateTo?: string;
}

function buildFilterQuery(params: DashboardFilterParams): string {
  const qs = new URLSearchParams();
  if (params.currency) qs.append('currency', params.currency);
  if (params.dateFrom) qs.append('date_from', params.dateFrom);
  if (params.dateTo) qs.append('date_to', params.dateTo);
  return qs.toString();
}

// --- API functions ---

export async function getDashboardOverview(
  params: DashboardFilterParams = {},
): Promise<DashboardOverview> {
  const query = buildFilterQuery(params);
  const url = `/dashboard/overview${query ? `?${query}` : ''}`;
  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch dashboard overview');
  const raw: DashboardOverviewRaw = await res.json();
  return mapOverview(raw);
}

export async function getDashboardEvolution(
  params: DashboardFilterParams = {},
): Promise<DashboardEvolution> {
  const query = buildFilterQuery(params);
  const url = `/dashboard/evolution${query ? `?${query}` : ''}`;
  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch dashboard evolution');
  const raw: DashboardEvolutionRaw = await res.json();
  return {
    points: raw.points.map(mapEvolutionPoint),
    currency: raw.currency,
    skippedCurrencies: raw.skipped_currencies ?? [],
  };
}

export async function getDashboardComposition(
  params: Omit<DashboardFilterParams, 'dateFrom' | 'dateTo'> = {},
): Promise<DashboardComposition> {
  const qs = new URLSearchParams();
  if (params.currency) qs.append('currency', params.currency);
  const query = qs.toString();
  const url = `/dashboard/composition${query ? `?${query}` : ''}`;
  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch dashboard composition');
  const raw: DashboardCompositionRaw = await res.json();
  return {
    items: raw.items.map(mapCompositionItem),
    totalAssets: Number(raw.total_assets),
    totalLiabilities: Number(raw.total_liabilities),
    currency: raw.currency,
    skippedCurrencies: raw.skipped_currencies ?? [],
  };
}

export async function getDashboardLiquidity(
  params: Omit<DashboardFilterParams, 'dateFrom' | 'dateTo'> = {},
): Promise<DashboardLiquidity> {
  const qs = new URLSearchParams();
  if (params.currency) qs.append('currency', params.currency);
  const query = qs.toString();
  const url = `/dashboard/liquidity${query ? `?${query}` : ''}`;
  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch dashboard liquidity');
  const raw: DashboardLiquidityRaw = await res.json();
  return mapLiquidity(raw);
}
