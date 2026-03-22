'use client';

import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ToggleGroup,
  ToggleGroupItem,
} from '@repo/ui/components';
import type { PortfolioEvolution } from '@/lib/api/metrics';
import {
  AREA_CURVE_TYPE,
  AREA_FILL_GRADIENT_ID,
  AREA_GRADIENT_END_OFFSET,
  AREA_GRADIENT_END_OPACITY,
  AREA_GRADIENT_START_OFFSET,
  AREA_GRADIENT_START_OPACITY,
  AREA_STROKE_WIDTH,
  AXIS_FONT_SIZE,
  AXIS_LINE,
  AXIS_TICK_LINE,
  AXIS_TICK_MARGIN,
  CHART_COLOR_PRIMARY,
  CHART_HEIGHT,
  CHART_MARGIN,
  FORMAT_THRESHOLD_MILLION,
  FORMAT_THRESHOLD_THOUSAND,
  GRID_STROKE_DASHARRAY,
  GRID_VERTICAL,
  TOOLTIP_BG,
  TOOLTIP_BORDER,
  TOOLTIP_BORDER_RADIUS,
  TOOLTIP_CURSOR_STROKE_WIDTH,
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
  Y_AXIS_WIDTH,
} from '@/lib/constants/charts';

const MONTHS_1 = 1;
const MONTHS_3 = 3;

type Period = '1m' | '3m' | 'ytd' | 'all';

// Formats a date string (YYYY-MM-DD) as "Jan 25".
function formatMonth(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

// Formats a number as a compact value for the Y axis.
function formatAxisValue(value: number): string {
  if (value >= FORMAT_THRESHOLD_MILLION) return `${(value / FORMAT_THRESHOLD_MILLION).toFixed(1)}M`;
  if (value >= FORMAT_THRESHOLD_THOUSAND)
    return `${(value / FORMAT_THRESHOLD_THOUSAND).toFixed(0)}K`;
  return value.toFixed(0);
}

// Filters evolution points based on the selected period.
function filterByPeriod(
  points: PortfolioEvolution['points'],
  period: Period,
): PortfolioEvolution['points'] {
  if (period === 'all' || points.length === 0) return points;

  const now = new Date();

  if (period === 'ytd') {
    const yearStart = `${now.getFullYear()}-01-01`;
    return points.filter((p) => p.date >= yearStart);
  }

  const months = period === '1m' ? MONTHS_1 : MONTHS_3;
  const cutoff = new Date(now.getFullYear(), now.getMonth() - months, 1);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  return points.filter((p) => p.date >= cutoffStr);
}

interface EvolutionSectionProps {
  evolution: PortfolioEvolution;
}

export function EvolutionSection({ evolution }: EvolutionSectionProps) {
  const t = useTranslations('dashboard');
  const [period, setPeriod] = useState<Period>('all');

  const filteredPoints = useMemo(
    () => filterByPeriod(evolution.points, period),
    [evolution.points, period],
  );

  const hasData = filteredPoints.length > 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('chart.title')}
        </CardTitle>
        <ToggleGroup
          type="single"
          value={period}
          onValueChange={(v) => {
            if (v) setPeriod(v as Period);
          }}
          variant="outline"
          size="sm"
        >
          <ToggleGroupItem value="1m">{t('period.1m')}</ToggleGroupItem>
          <ToggleGroupItem value="3m">{t('period.3m')}</ToggleGroupItem>
          <ToggleGroupItem value="ytd">{t('period.ytd')}</ToggleGroupItem>
          <ToggleGroupItem value="all">{t('period.all')}</ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent className="px-6 pb-6">
        {hasData ? (
          <div style={{ height: CHART_HEIGHT }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={filteredPoints} margin={CHART_MARGIN}>
                <CartesianGrid vertical={GRID_VERTICAL} strokeDasharray={GRID_STROKE_DASHARRAY} />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatMonth}
                  tickLine={AXIS_TICK_LINE}
                  axisLine={AXIS_LINE}
                  tickMargin={AXIS_TICK_MARGIN}
                  fontSize={AXIS_FONT_SIZE}
                />
                <YAxis
                  tickFormatter={formatAxisValue}
                  tickLine={AXIS_TICK_LINE}
                  axisLine={AXIS_LINE}
                  tickMargin={AXIS_TICK_MARGIN}
                  width={Y_AXIS_WIDTH}
                  fontSize={AXIS_FONT_SIZE}
                />
                <Tooltip
                  labelFormatter={(label) => formatMonth(String(label))}
                  formatter={(value) => [formatAxisValue(Number(value)), t('chart.tooltipValue')]}
                  contentStyle={{
                    backgroundColor: TOOLTIP_BG,
                    color: TOOLTIP_TEXT,
                    borderRadius: TOOLTIP_BORDER_RADIUS,
                    border: TOOLTIP_BORDER,
                    fontSize: TOOLTIP_FONT_SIZE,
                  }}
                  labelStyle={{ color: TOOLTIP_TEXT }}
                  itemStyle={{ color: TOOLTIP_TEXT }}
                  cursor={{ stroke: CHART_COLOR_PRIMARY, strokeWidth: TOOLTIP_CURSOR_STROKE_WIDTH }}
                />
                <defs>
                  <linearGradient id={AREA_FILL_GRADIENT_ID} x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset={AREA_GRADIENT_START_OFFSET}
                      stopColor={CHART_COLOR_PRIMARY}
                      stopOpacity={AREA_GRADIENT_START_OPACITY}
                    />
                    <stop
                      offset={AREA_GRADIENT_END_OFFSET}
                      stopColor={CHART_COLOR_PRIMARY}
                      stopOpacity={AREA_GRADIENT_END_OPACITY}
                    />
                  </linearGradient>
                </defs>
                <Area
                  type={AREA_CURVE_TYPE}
                  dataKey="totalValue"
                  stroke={CHART_COLOR_PRIMARY}
                  fill={`url(#${AREA_FILL_GRADIENT_ID})`}
                  strokeWidth={AREA_STROKE_WIDTH}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={{ height: CHART_HEIGHT }} className="flex items-center justify-center">
            <p className="text-paragraph-sm text-muted-foreground">{t('noData')}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
