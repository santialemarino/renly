'use client';

import { TrendingDown, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PortfolioMetrics } from '@/lib/api/metrics';

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

interface MetricCardsProps {
  metrics: PortfolioMetrics;
}

export function MetricCards({ metrics }: MetricCardsProps) {
  const t = useTranslations('dashboard');

  const isReturnPositive = (metrics.totalReturnPct ?? 0) >= 0;
  const isChangePositive = (metrics.monthChangePct ?? 0) >= 0;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {/* Total Value */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.totalValue')}</span>
        <p className="text-heading-3">{formatValue(metrics.totalValue)}</p>
      </Card>

      {/* Total Return */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.totalReturn')}</span>
        <div className="flex items-center gap-x-2">
          <p
            className={cn('text-heading-3', isReturnPositive ? 'text-emerald-600' : 'text-red-500')}
          >
            {metrics.totalReturnPct !== null ? formatPct(metrics.totalReturnPct) : '—'}
          </p>
          {metrics.totalReturnPct !== null &&
            (isReturnPositive ? (
              <TrendingUp className="size-5 text-emerald-600" />
            ) : (
              <TrendingDown className="size-5 text-red-500" />
            ))}
        </div>
      </Card>

      {/* Month Change */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.monthChange')}</span>
        <div className="flex items-center gap-x-2">
          <p
            className={cn('text-heading-3', isChangePositive ? 'text-emerald-600' : 'text-red-500')}
          >
            {metrics.monthChange !== null ? formatValue(metrics.monthChange) : '—'}
          </p>
          {metrics.monthChangePct !== null && (
            <span
              className={cn(
                'text-paragraph-sm',
                isChangePositive ? 'text-emerald-600' : 'text-red-500',
              )}
            >
              {formatPct(metrics.monthChangePct)}
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}
