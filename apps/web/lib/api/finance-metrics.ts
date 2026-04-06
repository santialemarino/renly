import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface FinanceOverviewRaw {
  total_income: string;
  total_expenses: string;
  net: string;
  income_change_pct: string | null;
  expense_change_pct: string | null;
  credit_card_balance: string;
  currency: string | null;
}

interface MonthlyPointRaw {
  date: string;
  income: string;
  expenses: string;
}

interface FinanceMonthlyRaw {
  points: MonthlyPointRaw[];
  currency: string | null;
}

interface ExpenseCategoryItemRaw {
  category: string;
  value: string;
  percentage: string;
}

interface ExpenseBreakdownRaw {
  items: ExpenseCategoryItemRaw[];
  total_expenses: string;
  currency: string | null;
}

interface IncomeCategoryItemRaw {
  category: string;
  value: string;
  percentage: string;
}

interface IncomeBreakdownRaw {
  items: IncomeCategoryItemRaw[];
  total_income: string;
  currency: string | null;
}

// --- Frontend types (camelCase) ---

export interface FinanceOverview {
  totalIncome: number;
  totalExpenses: number;
  net: number;
  incomeChangePct: number | null;
  expenseChangePct: number | null;
  creditCardBalance: number;
  currency: string | null;
}

export interface MonthlyPoint {
  date: string;
  income: number;
  expenses: number;
}

export interface FinanceMonthly {
  points: MonthlyPoint[];
  currency: string | null;
}

export interface ExpenseCategoryItem {
  category: string;
  value: number;
  percentage: number;
}

export interface ExpenseBreakdown {
  items: ExpenseCategoryItem[];
  totalExpenses: number;
  currency: string | null;
}

export interface IncomeCategoryItem {
  category: string;
  value: number;
  percentage: number;
}

export interface IncomeBreakdown {
  items: IncomeCategoryItem[];
  totalIncome: number;
  currency: string | null;
}

// --- Mappers ---

function mapOverview(raw: FinanceOverviewRaw): FinanceOverview {
  return {
    totalIncome: Number(raw.total_income),
    totalExpenses: Number(raw.total_expenses),
    net: Number(raw.net),
    incomeChangePct: raw.income_change_pct !== null ? Number(raw.income_change_pct) : null,
    expenseChangePct: raw.expense_change_pct !== null ? Number(raw.expense_change_pct) : null,
    creditCardBalance: Number(raw.credit_card_balance),
    currency: raw.currency,
  };
}

function mapMonthlyPoint(raw: MonthlyPointRaw): MonthlyPoint {
  return {
    date: raw.date,
    income: Number(raw.income),
    expenses: Number(raw.expenses),
  };
}

function mapExpenseCategoryItem(raw: ExpenseCategoryItemRaw): ExpenseCategoryItem {
  return {
    category: raw.category,
    value: Number(raw.value),
    percentage: Number(raw.percentage),
  };
}

function mapIncomeCategoryItem(raw: IncomeCategoryItemRaw): IncomeCategoryItem {
  return {
    category: raw.category,
    value: Number(raw.value),
    percentage: Number(raw.percentage),
  };
}

// --- Shared filter params ---

export interface FinanceMetricsFilterParams {
  currency?: string;
  dateFrom?: string;
  dateTo?: string;
}

function buildFilterQuery(params: FinanceMetricsFilterParams): string {
  const qs = new URLSearchParams();
  if (params.currency) qs.append('currency', params.currency);
  if (params.dateFrom) qs.append('date_from', params.dateFrom);
  if (params.dateTo) qs.append('date_to', params.dateTo);
  return qs.toString();
}

// --- API functions ---

export async function getFinanceOverview(
  params: FinanceMetricsFilterParams = {},
): Promise<FinanceOverview> {
  const query = buildFilterQuery(params);
  const url = `/finance-metrics/overview${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch finance overview');

  const raw: FinanceOverviewRaw = await res.json();
  return mapOverview(raw);
}

export async function getFinanceMonthly(
  params: FinanceMetricsFilterParams = {},
): Promise<FinanceMonthly> {
  const query = buildFilterQuery(params);
  const url = `/finance-metrics/monthly${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch finance monthly');

  const raw: FinanceMonthlyRaw = await res.json();
  return {
    points: raw.points.map(mapMonthlyPoint),
    currency: raw.currency,
  };
}

export async function getExpenseBreakdown(
  params: FinanceMetricsFilterParams = {},
): Promise<ExpenseBreakdown> {
  const query = buildFilterQuery(params);
  const url = `/finance-metrics/expense-breakdown${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch expense breakdown');

  const raw: ExpenseBreakdownRaw = await res.json();
  return {
    items: raw.items.map(mapExpenseCategoryItem),
    totalExpenses: Number(raw.total_expenses),
    currency: raw.currency,
  };
}

export async function getIncomeBreakdown(
  params: FinanceMetricsFilterParams = {},
): Promise<IncomeBreakdown> {
  const query = buildFilterQuery(params);
  const url = `/finance-metrics/income-breakdown${query ? `?${query}` : ''}`;

  const res = await authenticatedFetch(url, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch income breakdown');

  const raw: IncomeBreakdownRaw = await res.json();
  return {
    items: raw.items.map(mapIncomeCategoryItem),
    totalIncome: Number(raw.total_income),
    currency: raw.currency,
  };
}
