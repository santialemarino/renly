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
  CHART_COLOR_NEGATIVE,
  CHART_COLOR_POSITIVE,
  CHART_HEIGHT,
  CHART_MARGIN,
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
import { useFormatters } from '@/lib/i18n/formatters';

const BAR_COLOR_INCOME = CHART_COLOR_POSITIVE;
const BAR_COLOR_EXPENSES = CHART_COLOR_NEGATIVE;
const BAR_RADIUS = 4;

interface FinanceDashboardMonthlyChartProps {
  monthly: FinanceMonthly;
}

export function FinanceDashboardMonthlyChart({ monthly }: FinanceDashboardMonthlyChartProps) {
  const fmt = useFormatters();
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
