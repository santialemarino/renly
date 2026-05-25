'use client';

import { useLocale, useTranslations } from 'next-intl';
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
import { formatAxisValue, formatMonth } from '@/lib/utils/format';

interface InvestorDashboardEvolutionProps {
  evolution: PortfolioEvolution;
}

export function InvestorDashboardEvolution({ evolution }: InvestorDashboardEvolutionProps) {
  const locale = useLocale();
  const t = useTranslations('investorDashboard');

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
                  tickFormatter={(value) => formatMonth(String(value), locale)}
                  tickLine={AXIS_TICK_LINE}
                  axisLine={AXIS_LINE}
                  tickMargin={AXIS_TICK_MARGIN}
                  fontSize={AXIS_FONT_SIZE}
                />
                <YAxis
                  tickFormatter={(value) => formatAxisValue(Number(value), locale)}
                  tickLine={AXIS_TICK_LINE}
                  axisLine={AXIS_LINE}
                  tickMargin={AXIS_TICK_MARGIN}
                  width={Y_AXIS_WIDTH}
                  fontSize={AXIS_FONT_SIZE}
                />
                <Tooltip
                  animationDuration={TOOLTIP_ANIMATION_DURATION}
                  labelFormatter={(label) => formatMonth(String(label), locale)}
                  formatter={(value) => [
                    formatAxisValue(Number(value), locale),
                    t('chart.tooltipValue'),
                  ]}
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
