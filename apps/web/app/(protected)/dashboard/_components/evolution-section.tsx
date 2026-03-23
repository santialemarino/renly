'use client';

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

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
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
  CHART_ANIMATION_DURATION,
  CHART_ANIMATION_EASING,
  CHART_COLOR_PRIMARY,
  CHART_HEIGHT,
  CHART_MARGIN,
  FORMAT_THRESHOLD_MILLION,
  FORMAT_THRESHOLD_THOUSAND,
  GRID_STROKE_DASHARRAY,
  GRID_VERTICAL,
  TOOLTIP_ANIMATION_DURATION,
  TOOLTIP_BG,
  TOOLTIP_BORDER,
  TOOLTIP_BORDER_RADIUS,
  TOOLTIP_CURSOR_STROKE_WIDTH,
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
  Y_AXIS_WIDTH,
} from '@/lib/constants/charts';

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

interface EvolutionSectionProps {
  evolution: PortfolioEvolution;
}

export function EvolutionSection({ evolution }: EvolutionSectionProps) {
  const t = useTranslations('dashboard');

  const hasData = evolution.points.length > 0;

  return (
    <Card>
      <CardHeader className="px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('chart.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-6 pb-6">
        {hasData ? (
          <div style={{ height: CHART_HEIGHT }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={evolution.points} margin={CHART_MARGIN}>
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
                  animationDuration={TOOLTIP_ANIMATION_DURATION}
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
                  animationDuration={CHART_ANIMATION_DURATION}
                  animationEasing={CHART_ANIMATION_EASING}
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
