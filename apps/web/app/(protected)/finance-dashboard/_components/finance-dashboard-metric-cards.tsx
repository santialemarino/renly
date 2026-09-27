'use client';

import { CreditCard, TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { MetricCard, MetricCardGrid } from '@/components/metric-card';
import type { FinanceOverview } from '@/lib/api/finance-metrics';
import { valueColor } from '@/lib/i18n/format';
import { useFormatters } from '@/lib/i18n/formatters';

interface FinanceDashboardMetricCardsProps {
  overview: FinanceOverview;
}

export function FinanceDashboardMetricCards({ overview }: FinanceDashboardMetricCardsProps) {
  const fmt = useFormatters();
  const t = useTranslations('financeDashboard');

  return (
    <MetricCardGrid count={4}>
      {/* Total Income */}
      <MetricCard
        label={t('cards.totalIncome')}
        amount={overview.totalIncome}
        figureClassName="text-emerald-600"
      >
        {overview.incomeChangePct !== null && overview.incomeChangePct !== 0 && (
          <div className="flex items-center gap-x-1">
            <span className={cn('text-paragraph-xs', valueColor(overview.incomeChangePct))}>
              {fmt.signedPct(overview.incomeChangePct)} {t('cards.vsPreviousPeriod')}
            </span>
            {overview.incomeChangePct > 0 ? (
              <TrendingUp className="size-3.5 text-emerald-600" />
            ) : (
              <TrendingDown className="size-3.5 text-red-500" />
            )}
          </div>
        )}
      </MetricCard>

      {/* Total Expenses */}
      <MetricCard
        label={t('cards.totalExpenses')}
        amount={overview.totalExpenses}
        figureClassName="text-red-500"
      >
        {overview.expenseChangePct !== null && overview.expenseChangePct !== 0 && (
          <div className="flex items-center gap-x-1">
            <span className={cn('text-paragraph-xs', valueColor(-overview.expenseChangePct))}>
              {fmt.signedPct(overview.expenseChangePct)} {t('cards.vsPreviousPeriod')}
            </span>
            {/* For expenses, up is bad (red), down is good (green). */}
            {overview.expenseChangePct > 0 ? (
              <TrendingUp className="size-3.5 text-red-500" />
            ) : (
              <TrendingDown className="size-3.5 text-emerald-600" />
            )}
          </div>
        )}
      </MetricCard>

      {/* Net Cash Flow */}
      <MetricCard
        label={t('cards.net')}
        amount={overview.net}
        figureClassName={valueColor(overview.net)}
        icon={overview.net === 0 ? undefined : overview.net > 0 ? TrendingUp : TrendingDown}
        iconClassName={overview.net > 0 ? 'text-emerald-600' : 'text-red-500'}
      />

      {/* Credit Card Balance */}
      <MetricCard
        label={t('cards.creditCardBalance')}
        amount={overview.creditCardBalance}
        figureClassName={overview.creditCardBalance > 0 ? 'text-red-500' : 'text-muted-foreground'}
        icon={overview.creditCardBalance > 0 ? CreditCard : undefined}
        iconClassName="text-red-500"
      />
    </MetricCardGrid>
  );
}
