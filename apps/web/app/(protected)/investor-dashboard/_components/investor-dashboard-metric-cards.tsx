'use client';

import { TrendingDown, TrendingUp } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PortfolioMetrics } from '@/lib/api/metrics';
import { formatSignedPct, formatSignedValue, formatValue, valueColor } from '@/lib/utils/format';

interface InvestorDashboardMetricCardsProps {
  metrics: PortfolioMetrics;
}

export function InvestorDashboardMetricCards({ metrics }: InvestorDashboardMetricCardsProps) {
  const locale = useLocale();
  const t = useTranslations('investorDashboard');

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Total Value */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.totalValue')}</span>
        <p className="text-heading-3">{formatValue(metrics.totalValue, { locale })}</p>
      </Card>

      {/* TWR */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.twr')}</span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(metrics.twr))}>
            {metrics.twr !== null ? formatSignedPct(metrics.twr, locale) : '—'}
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
            {metrics.irr !== null ? formatSignedPct(metrics.irr, locale) : '—'}
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
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.gain')}</span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(metrics.absoluteGain))}>
            {formatValue(metrics.absoluteGain, { locale })}
          </p>
          {metrics.totalReturnPct !== null && metrics.totalReturnPct !== 0 && (
            <span className={cn('text-paragraph-sm', valueColor(metrics.totalReturnPct))}>
              {formatSignedPct(metrics.totalReturnPct, locale)}
            </span>
          )}
        </div>
        {metrics.monthChange !== null && (
          <span className={cn('text-paragraph-xs', valueColor(metrics.monthChange))}>
            {formatSignedValue(metrics.monthChange, locale)}
            {metrics.monthChangePct !== null && metrics.monthChangePct !== 0 && (
              <> ({formatSignedPct(metrics.monthChangePct, locale)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
      </Card>
    </div>
  );
}
