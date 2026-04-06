'use client';

import { CreditCard, TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { FinanceOverview } from '@/lib/api/finance-metrics';

// Formats a number as a compact currency value.
function formatValue(value: number): string {
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(value);
}

// Formats a decimal ratio as a display percentage (e.g. 0.05 → "+5%").
function formatPct(pct: number): string {
  const val = pct * 100;
  const hasDecimals = Math.round(val * 10) % 10 !== 0;
  const s = hasDecimals ? val.toFixed(1) : val.toFixed(0);
  return pct >= 0 ? `+${s}%` : `${s}%`;
}

// Returns the color class: green for positive, red for negative, grey for zero/null.
function valueColor(value: number | null): string {
  if (value === null || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-emerald-600' : 'text-red-500';
}

interface FinanceDashboardMetricCardsProps {
  overview: FinanceOverview;
}

export function FinanceDashboardMetricCards({ overview }: FinanceDashboardMetricCardsProps) {
  const t = useTranslations('financeDashboard');

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Total Income */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.totalIncome')}</span>
        <p className="text-heading-3 text-emerald-600">{formatValue(overview.totalIncome)}</p>
        {overview.incomeChangePct !== null && overview.incomeChangePct !== 0 && (
          <div className="flex items-center gap-x-1">
            <span className={cn('text-paragraph-xs', valueColor(overview.incomeChangePct))}>
              {formatPct(overview.incomeChangePct)} {t('cards.vsPreviousPeriod')}
            </span>
            {overview.incomeChangePct > 0 ? (
              <TrendingUp className="size-3.5 text-emerald-600" />
            ) : (
              <TrendingDown className="size-3.5 text-red-500" />
            )}
          </div>
        )}
      </Card>

      {/* Total Expenses */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.totalExpenses')}</span>
        <p className="text-heading-3 text-red-500">{formatValue(overview.totalExpenses)}</p>
        {overview.expenseChangePct !== null && overview.expenseChangePct !== 0 && (
          <div className="flex items-center gap-x-1">
            <span className={cn('text-paragraph-xs', valueColor(-overview.expenseChangePct))}>
              {formatPct(overview.expenseChangePct)} {t('cards.vsPreviousPeriod')}
            </span>
            {/* For expenses, up is bad (red), down is good (green). */}
            {overview.expenseChangePct > 0 ? (
              <TrendingUp className="size-3.5 text-red-500" />
            ) : (
              <TrendingDown className="size-3.5 text-emerald-600" />
            )}
          </div>
        )}
      </Card>

      {/* Net Cash Flow */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.net')}</span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(overview.net))}>
            {formatValue(overview.net)}
          </p>
          {overview.net !== 0 &&
            (overview.net > 0 ? (
              <TrendingUp className="size-5 text-emerald-600" />
            ) : (
              <TrendingDown className="size-5 text-red-500" />
            ))}
        </div>
      </Card>

      {/* Credit Card Balance */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">
          {t('cards.creditCardBalance')}
        </span>
        <div className="flex items-center gap-x-2">
          <p
            className={cn(
              'text-heading-3',
              overview.creditCardBalance > 0 ? 'text-red-500' : 'text-muted-foreground',
            )}
          >
            {formatValue(overview.creditCardBalance)}
          </p>
          {overview.creditCardBalance > 0 && <CreditCard className="size-5 text-red-500" />}
        </div>
      </Card>
    </div>
  );
}
