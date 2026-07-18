'use client';

import { TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PortfolioMetrics } from '@/lib/api/metrics';
import { valueColor } from '@/lib/i18n/format';
import { useFormatters } from '@/lib/i18n/formatters';

interface InvestorDashboardMetricCardsProps {
  metrics: PortfolioMetrics;
  hasPeriod?: boolean;
}

export function InvestorDashboardMetricCards({
  metrics,
  hasPeriod = false,
}: InvestorDashboardMetricCardsProps) {
  const t = useTranslations('investorDashboard');
  const fmt = useFormatters();

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Total Value */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">
          {t(hasPeriod ? 'cards.periodEndValue' : 'cards.totalValue')}
        </span>
        <p className="text-heading-3">{fmt.value(metrics.totalValue)}</p>
      </Card>

      {/* TWR */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.twr')}</span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(metrics.twr))}>
            {metrics.twr !== null ? fmt.signedPct(metrics.twr) : '—'}
          </p>
          {metrics.twr !== null &&
            metrics.twr !== 0 &&
            (metrics.twr > 0 ? (
              <TrendingUp className="size-5 text-emerald-600" />
            ) : (
              <TrendingDown className="size-5 text-red-500" />
            ))}
        </div>
      </Card>

      {/* IRR */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.irr')}</span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(metrics.irr))}>
            {metrics.irr !== null ? fmt.signedPct(metrics.irr) : '—'}
          </p>
          {metrics.irr !== null &&
            metrics.irr !== 0 &&
            (metrics.irr > 0 ? (
              <TrendingUp className="size-5 text-emerald-600" />
            ) : (
              <TrendingDown className="size-5 text-red-500" />
            ))}
        </div>
      </Card>

      {/* Gain + simple return % + month change subtext */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">
          {t(hasPeriod ? 'cards.periodGain' : 'cards.gain')}
        </span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(metrics.absoluteGain))}>
            {fmt.value(metrics.absoluteGain)}
          </p>
          {metrics.totalReturnPct !== null && metrics.totalReturnPct !== 0 && (
            <span className={cn('text-paragraph-sm', valueColor(metrics.totalReturnPct))}>
              {fmt.signedPct(metrics.totalReturnPct)}
            </span>
          )}
        </div>
        {metrics.monthChange !== null && (
          <span className={cn('text-paragraph-xs', valueColor(metrics.monthChange))}>
            {fmt.signedValue(metrics.monthChange)}
            {metrics.monthChangePct !== null && metrics.monthChangePct !== 0 && (
              <> ({fmt.signedPct(metrics.monthChangePct)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
      </Card>
    </div>
  );
}
