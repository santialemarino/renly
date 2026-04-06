'use client';

import { useTranslations } from 'next-intl';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import type { FinanceMonthly } from '@/lib/api/finance-metrics';
import {
  AXIS_FONT_SIZE,
  AXIS_LINE,
  AXIS_TICK_LINE,
  AXIS_TICK_MARGIN,
  CHART_ANIMATION_DURATION,
  CHART_ANIMATION_EASING,
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
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
  Y_AXIS_WIDTH,
} from '@/lib/constants/charts';

// oklch for emerald-600.
const BAR_COLOR_INCOME = 'oklch(0.596 0.145 163.225)';
// oklch for red-500.
const BAR_COLOR_EXPENSES = 'oklch(0.637 0.237 25.331)';
const BAR_RADIUS = 4;

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

interface FinanceDashboardMonthlyChartProps {
  monthly: FinanceMonthly;
}

export function FinanceDashboardMonthlyChart({ monthly }: FinanceDashboardMonthlyChartProps) {
  const t = useTranslations('financeDashboard');

  const hasData = monthly.points.length > 0;

  return (
    <Card>
      <CardHeader className="px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('monthlyChart.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-6 pb-6">
        {hasData ? (
          <div style={{ height: CHART_HEIGHT }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthly.points} margin={CHART_MARGIN}>
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
                  formatter={(value, name) => [
                    formatAxisValue(Number(value)),
                    name === 'income'
                      ? t('monthlyChart.tooltipIncome')
                      : t('monthlyChart.tooltipExpenses'),
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
                  cursor={false}
                />
                <Bar
                  dataKey="income"
                  fill={BAR_COLOR_INCOME}
                  radius={[BAR_RADIUS, BAR_RADIUS, 0, 0]}
                  animationDuration={CHART_ANIMATION_DURATION}
                  animationEasing={CHART_ANIMATION_EASING}
                />
                <Bar
                  dataKey="expenses"
                  fill={BAR_COLOR_EXPENSES}
                  radius={[BAR_RADIUS, BAR_RADIUS, 0, 0]}
                  animationDuration={CHART_ANIMATION_DURATION}
                  animationEasing={CHART_ANIMATION_EASING}
                />
              </BarChart>
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
