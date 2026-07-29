'use client';

import { useTranslations } from 'next-intl';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import type { CompositionItem } from '@/lib/api/dashboard';
import {
  CHART_ANIMATION_DURATION,
  CHART_ANIMATION_EASING,
  CHART_COLOR_NEGATIVE,
  CHART_COLOR_POSITIVE,
  DONUT_COLORS,
  DONUT_HEIGHT,
  DONUT_INNER_RADIUS,
  DONUT_OUTER_RADIUS,
  DONUT_PADDING_ANGLE,
  TOOLTIP_ANIMATION_DURATION,
  TOOLTIP_BG,
  TOOLTIP_BORDER,
  TOOLTIP_BORDER_RADIUS,
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
} from '@/lib/constants/charts';
import { useFormatters } from '@/lib/i18n/formatters';

const LIABILITIES_COLOR = CHART_COLOR_NEGATIVE;
const CASH_COLOR = CHART_COLOR_POSITIVE;

interface DashboardCompositionProps {
  composition: CompositionItem[];
}

export function DashboardComposition({ composition }: DashboardCompositionProps) {
  const fmt = useFormatters();
  const t = useTranslations('dashboard');
  const tCommon = useTranslations('common');

  const hasData = composition.length > 0;

  // Cash (asset) and liabilities get fixed colors; investment categories cycle DONUT_COLORS.
  function segmentName(label: string): string {
    if (label === 'liabilities') return t('composition.liabilities');
    if (label === 'cash') return t('composition.cash');
    return tCommon(`categories.${label}`);
  }
  const chartData = composition.map((item) => ({
    name: segmentName(item.label),
    value: item.value,
    percentage: item.percentage,
    isLiability: item.label === 'liabilities',
    isCash: item.label === 'cash',
  }));

  // Picks a segment's color: fixed for cash/liabilities, cycled DONUT_COLORS for investments.
  function segmentColor(
    entry: { isLiability: boolean; isCash: boolean },
    investmentIdx: () => number,
  ) {
    if (entry.isLiability) return LIABILITIES_COLOR;
    if (entry.isCash) return CASH_COLOR;
    return DONUT_COLORS[investmentIdx() % DONUT_COLORS.length];
  }

  let investmentIndex = 0;

  return (
    <Card className="flex-1">
      <CardHeader className="px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('composition.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-6">
        {hasData ? (
          <div className="flex flex-col gap-y-4">
            <div className="flex flex-col-reverse items-center gap-y-4 lg:flex-row lg:gap-x-6 lg:gap-y-0">
              {/* Legend */}
              <div className="w-full lg:flex-1 lg:min-w-0">
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 lg:flex lg:flex-col lg:gap-x-0">
                  {chartData.map((entry) => {
                    const color = segmentColor(entry, () => investmentIndex++);
                    return (
                      <div key={entry.name} className="flex items-center gap-x-2">
                        <div
                          className="size-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                        <span className="min-w-0 text-paragraph-xs text-muted-foreground truncate">
                          {entry.name}
                        </span>
                        <span className="shrink-0 text-paragraph-xs-semibold">
                          {fmt.pct(entry.percentage)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Donut chart */}
              <div style={{ height: DONUT_HEIGHT }} className="w-full max-w-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={chartData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={DONUT_INNER_RADIUS}
                      outerRadius={DONUT_OUTER_RADIUS}
                      paddingAngle={DONUT_PADDING_ANGLE}
                      animationDuration={CHART_ANIMATION_DURATION}
                      animationEasing={CHART_ANIMATION_EASING}
                    >
                      {(() => {
                        let idx = 0;
                        return chartData.map((entry) => (
                          <Cell key={entry.name} fill={segmentColor(entry, () => idx++)} />
                        ));
                      })()}
                    </Pie>
                    <Tooltip
                      animationDuration={TOOLTIP_ANIMATION_DURATION}
                      formatter={(value) => [fmt.value(Number(value), { compact: true })]}
                      contentStyle={{
                        backgroundColor: TOOLTIP_BG,
                        color: TOOLTIP_TEXT,
                        borderRadius: TOOLTIP_BORDER_RADIUS,
                        border: TOOLTIP_BORDER,
                        fontSize: TOOLTIP_FONT_SIZE,
                      }}
                      labelStyle={{ color: TOOLTIP_TEXT }}
                      itemStyle={{ color: TOOLTIP_TEXT }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ height: DONUT_HEIGHT }} className="flex items-center justify-center">
            <p className="text-paragraph-sm text-muted-foreground">{t('noData')}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
