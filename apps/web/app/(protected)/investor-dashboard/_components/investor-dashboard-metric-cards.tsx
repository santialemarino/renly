'use client';

import { TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { MetricCard, MetricCardGrid } from '@/components/metric-card';
import { MoneyFigure } from '@/components/money-figure';
import type { PortfolioMetrics } from '@/lib/api/metrics';
import { valueColor } from '@/lib/i18n/format';
import { useFormatters } from '@/lib/i18n/formatters';

// The trend arrow for a return, or none at all when there is no return or it is exactly flat.
function trendIcon(value: number | null) {
  if (value === null || value === 0) return undefined;
  return value > 0 ? TrendingUp : TrendingDown;
}

interface InvestorDashboardMetricCardsProps {
  metrics: PortfolioMetrics;
  hasPeriod?: boolean;
}

export function InvestorDashboardMetricCards({
  metrics,
  hasPeriod = false,
}: InvestorDashboardMetricCardsProps) {
  const fmt = useFormatters();
  const t = useTranslations('investorDashboard');

  return (
    <MetricCardGrid count={4}>
      {/* Total Value */}
      <MetricCard
        label={t(hasPeriod ? 'cards.periodEndValue' : 'cards.totalValue')}
        amount={metrics.totalValue}
      />

      {/* TWR */}
      <MetricCard
        label={t('cards.twr')}
        text={metrics.twr !== null ? fmt.signedPct(metrics.twr) : '—'}
        figureClassName={valueColor(metrics.twr)}
        icon={trendIcon(metrics.twr)}
        iconClassName={
          metrics.twr !== null && metrics.twr > 0 ? 'text-emerald-600' : 'text-red-500'
        }
      />

      {/* IRR */}
      <MetricCard
        label={t('cards.irr')}
        text={metrics.irr !== null ? fmt.signedPct(metrics.irr) : '—'}
        figureClassName={valueColor(metrics.irr)}
        icon={trendIcon(metrics.irr)}
        iconClassName={
          metrics.irr !== null && metrics.irr > 0 ? 'text-emerald-600' : 'text-red-500'
        }
      />

      {/* Gain + simple return % + month change subtext */}
      <MetricCard
        label={t(hasPeriod ? 'cards.periodGain' : 'cards.gain')}
        amount={metrics.absoluteGain}
        figureClassName={valueColor(metrics.absoluteGain)}
        trailing={
          metrics.totalReturnPct !== null &&
          metrics.totalReturnPct !== 0 && (
            <span className={cn('text-paragraph-sm', valueColor(metrics.totalReturnPct))}>
              {fmt.signedPct(metrics.totalReturnPct)}
            </span>
          )
        }
      >
        {metrics.monthChange !== null && (
          <span className={cn('text-paragraph-xs', valueColor(metrics.monthChange))}>
            <MoneyFigure>{fmt.signedValue(metrics.monthChange)}</MoneyFigure>
            {metrics.monthChangePct !== null && metrics.monthChangePct !== 0 && (
              <> ({fmt.signedPct(metrics.monthChangePct)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
      </MetricCard>
    </MetricCardGrid>
  );
}
