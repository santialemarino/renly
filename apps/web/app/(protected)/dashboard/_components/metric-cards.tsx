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

// Formats a number with explicit +/- sign.
function formatSignedValue(value: number): string {
  const formatted = formatValue(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

// Returns the color class: green for positive, red for negative, grey for zero/null.
function valueColor(value: number | null): string {
  if (value === null || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-emerald-600' : 'text-red-500';
}

interface MetricCardsProps {
  metrics: PortfolioMetrics;
}

export function MetricCards({ metrics }: MetricCardsProps) {
  const t = useTranslations('dashboard');

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Total Value */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.totalValue')}</span>
        <p className="text-heading-3">{formatValue(metrics.totalValue)}</p>
      </Card>

      {/* TWR */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('cards.twr')}</span>
        <div className="flex items-center gap-x-2">
          <p className={cn('text-heading-3', valueColor(metrics.twr))}>
            {metrics.twr !== null ? formatPct(metrics.twr) : '—'}
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
            {metrics.irr !== null ? formatPct(metrics.irr) : '—'}
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
            {formatValue(metrics.absoluteGain)}
          </p>
          {metrics.totalReturnPct !== null && metrics.totalReturnPct !== 0 && (
            <span className={cn('text-paragraph-sm', valueColor(metrics.totalReturnPct))}>
              {formatPct(metrics.totalReturnPct)}
            </span>
          )}
        </div>
        {metrics.monthChange !== null && (
          <span className={cn('text-paragraph-mini', valueColor(metrics.monthChange))}>
            {formatSignedValue(metrics.monthChange)}
            {metrics.monthChangePct !== null && metrics.monthChangePct !== 0 && (
              <> ({formatPct(metrics.monthChangePct)})</>
            )}{' '}
            {t('cards.vsLastMonth')}
          </span>
        )}
      </Card>
    </div>
  );
}
