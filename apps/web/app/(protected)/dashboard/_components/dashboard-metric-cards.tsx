'use client';

import { CreditCard, Landmark, TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { DashboardOverview } from '@/lib/api/dashboard';
import { valueColor } from '@/lib/i18n/format';
import { useFormatters } from '@/lib/i18n/formatters';

interface DashboardMetricCardsProps {
  overview: DashboardOverview;
}

export function DashboardMetricCards({ overview }: DashboardMetricCardsProps) {
  const fmt = useFormatters();
  const t = useTranslations('dashboard');

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5"
      data-testid="dashboard-metrics"
    >
      {/* Net Worth */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.netWorth')}</span>
        <p className="text-heading-3">{fmt.value(overview.netWorth)}</p>
        {overview.netWorthChange !== null && (
          <span className={cn('text-paragraph-xs', valueColor(overview.netWorthChange))}>
            {fmt.signedValue(overview.netWorthChange)}
            {overview.netWorthChangePct !== null && overview.netWorthChangePct !== 0 && (
              <> ({fmt.signedPct(overview.netWorthChangePct)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
        <span className="text-paragraph-mini text-muted-foreground">{t('cards.netWorthHint')}</span>
      </Card>

      {/* Cash / bank balance */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.cash')}</span>
        <div className="flex items-center gap-x-2">
          <p className="text-heading-3">{fmt.value(overview.cashTotal)}</p>
          {overview.cashTotal !== 0 && <Landmark className="size-5 text-emerald-600" />}
        </div>
        <span className="text-paragraph-mini text-muted-foreground">{t('cards.cashHint')}</span>
      </Card>

      {/* Investment Value + gain subtext */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">
          {t('cards.investmentValue')}
        </span>
        <p className="text-heading-3">{fmt.value(overview.investmentTotal)}</p>
        <div className="flex items-center gap-x-1.5">
          {overview.investmentGain !== 0 && (
            <span className={cn('text-paragraph-xs', valueColor(overview.investmentGain))}>
              {fmt.signedValue(overview.investmentGain)}
              {overview.investmentGainPct !== null && overview.investmentGainPct !== 0 && (
                <> ({fmt.signedPct(overview.investmentGainPct)})</>
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
            {fmt.value(overview.totalIncome - overview.totalExpenses)}
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
            {fmt.value(overview.creditCardBalance)}
          </p>
          {overview.creditCardBalance > 0 && <CreditCard className="size-5 text-red-500" />}
        </div>
        {/* The last of the three money cards to get a hint, and the one that most needed it: a bucket
            in another currency is valued at the user's chosen dollar rate, while the bill will be
            settled at the "dólar tarjeta" rate — so this figure is what is owed today, not a quote for
            clearing it. Help's currency section carries the full explanation. */}
        <span className="text-paragraph-mini text-muted-foreground">
          {t('cards.creditCardBalanceHint')}
        </span>
      </Card>
    </div>
  );
}
