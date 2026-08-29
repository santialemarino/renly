'use client';

import { LineChartIcon } from 'lucide-react';
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

import {
  seriesHasShare,
  showsCoverage,
  valuedPointCount,
} from '@/app/(protected)/shared/pot-rules';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import type { PotValueSeries } from '@/lib/api/pots';
import {
  AREA_CURVE_TYPE,
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
  POINT_DOT_RADIUS,
  POINT_DOT_RADIUS_ACTIVE,
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

// Its own gradient id: two charts on one page sharing one id makes the second reuse the first's stops.
const POT_AREA_GRADIENT_ID = 'fillPotValue';

interface PotValueSectionProps {
  series: PotValueSeries;
  baseCurrency: string;
}

/*
 * What the pot has been worth over time, at its declared cadence, with the viewer's own share drawn
 * inside it — the monitoring half of V5.
 *
 * The two marks encode a part-of-whole relationship rather than two independent categories: the filled
 * area is everything the pot holds and the line inside it is the reader's slice of that, so the same
 * hue at two steps says more than two unrelated colours would. Both series are the same measure in the
 * same currency, so they share one axis.
 *
 * GAPS ARE THE POINT and must not be smoothed over. A point is null wherever the pot's value cannot be
 * stated in full on that date — which on a real pot is most of the early points, because a holding
 * moved in last month has no valuation for the months before it. `connectNulls` stays off so an
 * unknown period reads as a break, and every point carries a dot so a lone valued period is visible at
 * all rather than a line segment of zero length. The caption says how much of the window is actually
 * known, because a chart with two points and ten gaps should say so in words too.
 *
 * The share line is dropped entirely when the reader holds nothing anywhere in the window: a legend
 * entry for a line that is never drawn is a promise the chart does not keep.
 */
export function PotValueSection({ series, baseCurrency }: PotValueSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const valued = valuedPointCount(series);
  const hasShare = seriesHasShare(series);
  const isWeekly = series.interval === 'weekly';
  // A weekly point is a specific day, so it needs the day; a monthly one is the month it closes.
  const formatPointDate = (value: string) => (isWeekly ? fmt.date(value) : fmt.month(value));

  const data = series.points.map((point) => ({
    date: point.date,
    nav: point.nav === null ? null : Number(point.nav),
    myValue: point.myValue === null ? null : Number(point.myValue),
  }));

  const seriesNames: Record<string, string> = {
    nav: t('pots.series.legend.pot'),
    myValue: t('pots.series.legend.myShare'),
  };

  return (
    <div className="flex flex-col gap-y-4">
      <SectionHeader
        title={t('pots.series.title')}
        description={
          showsCoverage(series)
            ? t(isWeekly ? 'pots.series.coverageWeekly' : 'pots.series.coverageMonthly', {
                valued,
                total: series.points.length,
              })
            : t('pots.series.description')
        }
      />

      {valued === 0 ? (
        <EmptyState
          icon={LineChartIcon}
          title={t('pots.series.emptyTitle')}
          description={t('pots.series.emptyDescription')}
        />
      ) : (
        <div style={{ height: CHART_HEIGHT }} className="w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={CHART_MARGIN}>
              <CartesianGrid vertical={GRID_VERTICAL} strokeDasharray={GRID_STROKE_DASHARRAY} />
              <XAxis
                dataKey="date"
                tickFormatter={(value) => formatPointDate(String(value))}
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
                labelFormatter={(label) => formatPointDate(String(label))}
                formatter={(value, name) => [
                  fmt.amount(String(value), baseCurrency),
                  seriesNames[String(name)] ?? String(name),
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
              {/*
               * Identity is never colour alone: two series always carry a legend. Its height is
               * stated rather than measured, so the plot area does not reflow above it once the
               * legend's own size is known — the same layout-shift rule the rest of the app follows.
               */}
              <Legend
                verticalAlign="bottom"
                height={LEGEND_HEIGHT}
                formatter={(value) => seriesNames[String(value)] ?? String(value)}
                wrapperStyle={{ fontSize: LEGEND_FONT_SIZE }}
              />
              <defs>
                <linearGradient id={POT_AREA_GRADIENT_ID} x1="0" y1="0" x2="0" y2="1">
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
                dataKey="nav"
                stroke={CHART_COLOR_PRIMARY}
                fill={`url(#${POT_AREA_GRADIENT_ID})`}
                strokeWidth={AREA_STROKE_WIDTH}
                connectNulls={false}
                dot={{ r: POINT_DOT_RADIUS, fill: CHART_COLOR_PRIMARY, strokeWidth: 0 }}
                activeDot={{ r: POINT_DOT_RADIUS_ACTIVE }}
                animationDuration={CHART_ANIMATION_DURATION}
                animationEasing={CHART_ANIMATION_EASING}
              />
              {hasShare && (
                <Line
                  type={AREA_CURVE_TYPE}
                  dataKey="myValue"
                  stroke={CHART_COLOR_SECONDARY}
                  strokeWidth={AREA_STROKE_WIDTH}
                  connectNulls={false}
                  dot={{ r: POINT_DOT_RADIUS, fill: CHART_COLOR_SECONDARY, strokeWidth: 0 }}
                  activeDot={{ r: POINT_DOT_RADIUS_ACTIVE }}
                  animationDuration={CHART_ANIMATION_DURATION}
                  animationEasing={CHART_ANIMATION_EASING}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
