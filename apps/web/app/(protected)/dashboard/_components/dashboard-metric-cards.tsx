'use client';

import { CreditCard, TrendingDown, TrendingUp } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { DashboardOverview } from '@/lib/api/dashboard';
import { formatSignedPct, formatSignedValue, formatValue, valueColor } from '@/lib/utils/format';

interface DashboardMetricCardsProps {
  overview: DashboardOverview;
}

export function DashboardMetricCards({ overview }: DashboardMetricCardsProps) {
  const locale = useLocale();
  const t = useTranslations('dashboard');

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      data-testid="dashboard-metrics"
    >
      {/* Net Worth */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.netWorth')}</span>
        <p className="text-heading-3">{formatValue(overview.netWorth, { locale })}</p>
        {overview.netWorthChange !== null && (
          <span className={cn('text-paragraph-xs', valueColor(overview.netWorthChange))}>
            {formatSignedValue(overview.netWorthChange, locale)}
            {overview.netWorthChangePct !== null && overview.netWorthChangePct !== 0 && (
              <> ({formatSignedPct(overview.netWorthChangePct, locale)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
        <span className="text-paragraph-mini text-muted-foreground">{t('cards.netWorthHint')}</span>
      </Card>

      {/* Investment Value + gain subtext */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">
          {t('cards.investmentValue')}
        </span>
        <p className="text-heading-3">{formatValue(overview.investmentTotal, { locale })}</p>
        <div className="flex items-center gap-x-1.5">
          {overview.investmentGain !== 0 && (
            <span className={cn('text-paragraph-xs', valueColor(overview.investmentGain))}>
              {formatSignedValue(overview.investmentGain, locale)}
              {overview.investmentGainPct !== null && overview.investmentGainPct !== 0 && (
                <> ({formatSignedPct(overview.investmentGainPct, locale)})</>
              )}
            </span>
          )}
        </div>
      </Card>

      {/* Net Cash Flow */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.netCashFlow')}</span>
        <div className="flex items-center gap-x-2">
          <p
            className={cn(
              'text-heading-3',
              valueColor(overview.totalIncome - overview.totalExpenses),
            )}
          >
            {formatValue(overview.totalIncome - overview.totalExpenses, { locale })}
          </p>
          {overview.totalIncome - overview.totalExpenses !== 0 &&
            (overview.totalIncome - overview.totalExpenses > 0 ? (
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
            {formatValue(overview.creditCardBalance, { locale })}
          </p>
          {overview.creditCardBalance > 0 && <CreditCard className="size-5 text-red-500" />}
        </div>
      </Card>
    </div>
  );
}
