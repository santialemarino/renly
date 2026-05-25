'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import type { ExpenseBreakdown, IncomeBreakdown } from '@/lib/api/finance-metrics';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import {
  CHART_ANIMATION_DURATION,
  CHART_ANIMATION_EASING,
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
import { formatPct, formatValue } from '@/lib/utils/format';

type Mode = 'expense' | 'income';

interface FinanceDashboardDistributionProps {
  expenseBreakdown: ExpenseBreakdown;
  incomeBreakdown: IncomeBreakdown;
}

export function FinanceDashboardDistribution({
  expenseBreakdown,
  incomeBreakdown,
}: FinanceDashboardDistributionProps) {
  const t = useTranslations('financeDashboard');
  const tExpenses = useTranslations('expenses');
  const tIncome = useTranslations('income');
  const [mode, setMode] = useState<Mode>('expense');

  const isExpenseMode = mode === 'expense';

  const chartData = isExpenseMode
    ? expenseBreakdown.items.map((item) => ({
        name: tExpenses(`categories.${item.category}`),
        value: item.value,
        percentage: item.percentage,
      }))
    : incomeBreakdown.items.map((item) => ({
        name: tIncome(`categories.${item.category}`),
        value: item.value,
        percentage: item.percentage,
      }));

  const hasData = chartData.length > 0;

  // Measure legend height for smooth bottom-edge animation.
  const legendRef = useRef<HTMLDivElement>(null);
  const [legendHeight, setLegendHeight] = useState<number>(0);
  const initialized = useRef(false);

  useEffect(() => {
    const el = legendRef.current;
    if (!el) return;

    // Set initial height without transition to avoid flash.
    if (!initialized.current) {
      setLegendHeight(el.scrollHeight);
      initialized.current = true;
    }

    const observer = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height;
      if (h != null) setLegendHeight(h);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Card className="flex-1">
      <CardHeader className="flex flex-row items-center justify-between px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('distribution.title')}
        </CardTitle>
        <PillToggleGroup
          items={[
            { value: 'expense', label: t('distribution.byExpense') },
            { value: 'income', label: t('distribution.byIncome') },
          ]}
          value={mode}
          onValueChange={(v) => setMode(v as Mode)}
        />
      </CardHeader>
      <CardContent className="px-6">
        {hasData ? (
          <div
            className="overflow-hidden transition-[height] duration-300 ease-in-out"
            style={{ height: legendHeight }}
          >
            <div ref={legendRef} className="flex flex-col gap-y-4">
              {/* Chart (top on mobile, right on desktop) + Legend */}
              <div className="flex flex-col-reverse items-center gap-y-4 lg:flex-row lg:gap-x-6 lg:gap-y-0">
                {/* Legend items — content fades on mode switch. */}
                <div className="w-full lg:min-w-0 lg:flex-1">
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                      key={mode}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: ANIMATION_DEFAULT }}
                      className="grid grid-cols-2 gap-x-4 gap-y-2 lg:flex lg:flex-col lg:gap-x-0"
                    >
                      {chartData.map((entry, index) => (
                        <div key={entry.name} className="flex items-center gap-x-2">
                          <div
                            className="size-2.5 shrink-0 rounded-full"
                            style={{
                              backgroundColor: DONUT_COLORS[index % DONUT_COLORS.length],
                            }}
                          />
                          <span className="min-w-0 text-paragraph-xs text-muted-foreground truncate">
                            {entry.name}
                          </span>
                          <span className="shrink-0 text-paragraph-xs-semibold">
                            {formatPct(entry.percentage)}%
                          </span>
                        </div>
                      ))}
                    </motion.div>
                  </AnimatePresence>
                </div>

                {/* Donut chart — key forces remount so Recharts replays the draw animation. */}
                <div
                  style={{ height: DONUT_HEIGHT, maxWidth: DONUT_HEIGHT }}
                  className="w-full shrink-0"
                >
                  <ResponsiveContainer key={mode} width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={chartData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={DONUT_INNER_RADIUS}
                        outerRadius={DONUT_OUTER_RADIUS}
                        animationDuration={CHART_ANIMATION_DURATION}
                        animationEasing={CHART_ANIMATION_EASING}
                        paddingAngle={DONUT_PADDING_ANGLE}
                        strokeWidth={0}
                      >
                        {chartData.map((_entry, index) => (
                          <Cell key={index} fill={DONUT_COLORS[index % DONUT_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip
                        animationDuration={TOOLTIP_ANIMATION_DURATION}
                        formatter={(value) => formatValue(Number(value), { compact: true })}
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
