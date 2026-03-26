'use client';

import { useTranslations } from 'next-intl';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import type { InvestmentMetrics } from '@/lib/api/metrics';

// Formats a number as a compact currency value.
function formatValue(value: number): string {
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(value);
}

interface InvestmentDetailCardProps {
  metrics: InvestmentMetrics;
}

// Shows metrics complementary to the metric cards (which show value, TWR, IRR, gain).
// This card shows: invested capital, base currency, category, and data points.
export function InvestmentDetailCard({ metrics }: InvestmentDetailCardProps) {
  const t = useTranslations('dashboard');
  const tCommon = useTranslations('common');

  return (
    <Card>
      <CardHeader className="px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('detail.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-4 px-6 pb-6 md:grid-cols-4">
        {/* Invested Capital */}
        <div className="flex flex-col gap-y-1">
          <span className="text-paragraph-xs text-muted-foreground">{t('detail.invested')}</span>
          <span className="text-paragraph-semibold">{formatValue(metrics.investedCapital)}</span>
        </div>

        {/* Snapshots */}
        <div className="flex flex-col gap-y-1">
          <span className="text-paragraph-xs text-muted-foreground">{t('detail.dataPoints')}</span>
          <span className="text-paragraph-semibold">{metrics.periodReturns.length}</span>
        </div>

        {/* Category */}
        <div className="flex flex-col gap-y-1">
          <span className="text-paragraph-xs text-muted-foreground">{t('detail.category')}</span>
          <span className="text-paragraph-semibold">
            {tCommon(`categories.${metrics.category}`)}
          </span>
        </div>

        {/* Base Currency */}
        <div className="flex flex-col gap-y-1">
          <span className="text-paragraph-xs text-muted-foreground">
            {t('detail.baseCurrency')}
          </span>
          <span className="text-paragraph-semibold">{metrics.baseCurrency}</span>
        </div>
      </CardContent>
    </Card>
  );
}
