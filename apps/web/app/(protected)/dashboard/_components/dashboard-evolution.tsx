'use client';

import { useTranslations } from 'next-intl';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import type { DashboardEvolution } from '@/lib/api/dashboard';
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
  CHART_COLOR_SECONDARY,
  CHART_HEIGHT,
  CHART_MARGIN,
  GRID_STROKE_DASHARRAY,
  GRID_VERTICAL,
  LEGEND_FONT_SIZE,
  LEGEND_HEIGHT,
  TOOLTIP_ANIMATION_DURATION,
  TOOLTIP_BG,
  TOOLTIP_BORDER,
  TOOLTIP_BORDER_RADIUS,
  TOOLTIP_CURSOR_STROKE_WIDTH,
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
  Y_AXIS_WIDTH,
} from '@/lib/constants/charts';
import { useFormatters } from '@/lib/i18n/formatters';

interface DashboardEvolutionProps {
  evolution: DashboardEvolution;
  // Whether the reader has a shared side at all, which is what makes a second series meaningful.
  hasShared: boolean;
}

export function DashboardEvolutionChart({ evolution, hasShared }: DashboardEvolutionProps) {
  const fmt = useFormatters();
  const t = useTranslations('dashboard');

  const hasData = evolution.points.length > 0;
  /*
   * The second series is the part-of-whole pair the pot page already draws: the filled area is
   * everything the reader is worth and the line inside it is the half held in their own name, so the
   * gap between them IS the shared side over time. One hue at two steps rather than two colours,
   * because they are the same measure at two scopes — and dropped entirely for a solo user, where the
   * two lines would sit exactly on top of each other and the legend would promise a distinction the
   * chart does not draw.
   */
  const seriesNames: Record<string, string> = {
    netWorth: t('chart.legend.total'),
    privateNetWorth: t('chart.legend.yours'),
  };

  return (
    <Card className="flex-1">
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
                  tickFormatter={(value) => fmt.month(String(value))}
                  tickLine={AXIS_TICK_LINE}
                  axisLine={AXIS_LINE}
                  tickMargin={AXIS_TICK_MARGIN}
                  fontSize={AXIS_FONT_SIZE}
                />
                <YAxis
                  tickFormatter={(value) => fmt.axisValue(Number(value))}
                  tickLine={AXIS_TICK_LINE}
                  axisLine={AXIS_LINE}
                  tickMargin={AXIS_TICK_MARGIN}
                  width={Y_AXIS_WIDTH}
                  fontSize={AXIS_FONT_SIZE}
                />
                <Tooltip
                  animationDuration={TOOLTIP_ANIMATION_DURATION}
                  labelFormatter={(label) => fmt.month(String(label))}
                  formatter={(value, name) => [
                    fmt.axisValue(Number(value)),
                    hasShared
                      ? (seriesNames[String(name)] ?? String(name))
                      : t('chart.tooltipValue'),
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
                {/*
                 * Identity is never colour alone, so two series carry a legend — with its height
                 * stated rather than measured, or the plot area reflows once the legend is sized.
                 */}
                {hasShared && (
                  <Legend
                    verticalAlign="bottom"
                    height={LEGEND_HEIGHT}
                    formatter={(value) => seriesNames[String(value)] ?? String(value)}
                    wrapperStyle={{ fontSize: LEGEND_FONT_SIZE }}
                  />
                )}
                <Area
                  type={AREA_CURVE_TYPE}
                  dataKey="netWorth"
                  stroke={CHART_COLOR_PRIMARY}
                  fill={`url(#${AREA_FILL_GRADIENT_ID})`}
                  strokeWidth={AREA_STROKE_WIDTH}
                  animationDuration={CHART_ANIMATION_DURATION}
                  animationEasing={CHART_ANIMATION_EASING}
                />
                {hasShared && (
                  <Line
                    type={AREA_CURVE_TYPE}
                    dataKey="privateNetWorth"
                    stroke={CHART_COLOR_SECONDARY}
                    strokeWidth={AREA_STROKE_WIDTH}
                    dot={false}
                    animationDuration={CHART_ANIMATION_DURATION}
                    animationEasing={CHART_ANIMATION_EASING}
                  />
                )}
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
