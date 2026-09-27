'use client';

import { CreditCard, Landmark, TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { DashboardSharedBreakdown } from '@/app/(protected)/dashboard/_components/dashboard-shared-breakdown';
import { MetricCard, MetricCardGrid } from '@/components/metric-card';
import { MoneyFigure } from '@/components/money-figure';
import type { DashboardOverview } from '@/lib/api/dashboard';
import { valueColor } from '@/lib/i18n/format';
import { useFormatters } from '@/lib/i18n/formatters';

interface DashboardMetricCardsProps {
  overview: DashboardOverview;
}

export function DashboardMetricCards({ overview }: DashboardMetricCardsProps) {
  const fmt = useFormatters();
  const t = useTranslations('dashboard');

  const netCashFlow = overview.totalIncome - overview.totalExpenses;

  return (
    <MetricCardGrid count={5} testId="dashboard-metrics">
      {/* Net Worth */}
      <MetricCard label={t('cards.netWorth')} amount={overview.netWorth}>
        {overview.netWorthChange !== null && (
          <span className={cn('text-paragraph-xs', valueColor(overview.netWorthChange))}>
            <MoneyFigure>{fmt.signedValue(overview.netWorthChange)}</MoneyFigure>
            {overview.netWorthChangePct !== null && overview.netWorthChangePct !== 0 && (
              <> ({fmt.signedPct(overview.netWorthChangePct)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
        <span className="text-paragraph-mini text-muted-foreground">{t('cards.netWorthHint')}</span>
        {/*
         * The headline decomposed where it stands, rather than in cards of its own: X1 keeps the total
         * as the answer to "what am I worth", and Yours/Shared says how it is held. Renders nothing at
         * all for a solo user.
         */}
        <DashboardSharedBreakdown overview={overview} />
      </MetricCard>

      {/* Cash / bank balance */}
      <MetricCard
        label={t('cards.cash')}
        amount={overview.cashTotal}
        icon={overview.cashTotal !== 0 ? Landmark : undefined}
        iconClassName="text-emerald-600"
      >
        {/*
         * Counts the user's own accounts PLUS their share of any a pot holds, which is the same money
         * the composition donut puts in its `cash` slice. Two figures on one screen calling themselves
         * cash and counting different things is the failure this avoids; the hint says which it is.
         */}
        <span className="text-paragraph-mini text-muted-foreground">
          {overview.hasShared ? t('cards.cashHintShared') : t('cards.cashHint')}
        </span>
      </MetricCard>

      {/* Investment Value + gain subtext */}
      <MetricCard label={t('cards.investmentValue')} amount={overview.investmentTotal}>
        <div className="flex items-center gap-x-1.5">
          {overview.investmentGain !== 0 && (
            <span className={cn('text-paragraph-xs', valueColor(overview.investmentGain))}>
              <MoneyFigure>{fmt.signedValue(overview.investmentGain)}</MoneyFigure>
              {overview.investmentGainPct !== null && overview.investmentGainPct !== 0 && (
                <> ({fmt.signedPct(overview.investmentGainPct)})</>
              )}
            </span>
          )}
        </div>
        {/*
         * The total counts co-owned holdings at the viewer's share; the GAIN above cannot. A pot share
         * has no invested figure of its own that is not the pot's ledger, and your exposure to it moves
         * every time units are issued — so a return attributed to you would be wrong in a way no
         * rounding explains. The line says whose return it is instead of quietly meaning less.
         */}
        {overview.hasShared && overview.investmentGain !== 0 && (
          <span className="text-paragraph-mini text-muted-foreground">
            {t('cards.investmentGainScope')}
          </span>
        )}
      </MetricCard>

      {/* Net Cash Flow */}
      <MetricCard
        label={t('cards.netCashFlow')}
        amount={netCashFlow}
        figureClassName={valueColor(netCashFlow)}
        icon={netCashFlow === 0 ? undefined : netCashFlow > 0 ? TrendingUp : TrendingDown}
        iconClassName={netCashFlow > 0 ? 'text-emerald-600' : 'text-red-500'}
      />

      {/* Credit Card Balance */}
      <MetricCard
        label={t('cards.creditCardBalance')}
        amount={overview.creditCardBalance}
        figureClassName={overview.creditCardBalance > 0 ? 'text-red-500' : 'text-muted-foreground'}
        icon={overview.creditCardBalance > 0 ? CreditCard : undefined}
        iconClassName="text-red-500"
      >
        {/* The last of the three money cards to get a hint, and the one that most needed it: a bucket
            in another currency is valued at the user's chosen dollar rate, while the bill will be
            settled at the "dólar tarjeta" rate — so this figure is what is owed today, not a quote for
            clearing it. Help's currency section carries the full explanation. */}
        <span className="text-paragraph-mini text-muted-foreground">
          {t('cards.creditCardBalanceHint')}
        </span>
      </MetricCard>
    </MetricCardGrid>
  );
}
