'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import type { AllocationResponse, GroupAllocationResponse } from '@/lib/api/metrics';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { UNGROUPED_LABEL } from '@/lib/constants/api-constants';
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
import { useFormatters } from '@/lib/i18n/formatters';

type Mode = 'category' | 'group';

interface InvestorDashboardDistributionProps {
  categoryAllocation: AllocationResponse;
  groupAllocation: GroupAllocationResponse;
  forcedMode?: Mode;
}

export function InvestorDashboardDistribution({
  categoryAllocation,
  groupAllocation,
  forcedMode,
}: InvestorDashboardDistributionProps) {
  const fmt = useFormatters();
  const t = useTranslations('investorDashboard');
  const tCommon = useTranslations('common');
  const [mode, setMode] = useState<Mode>(forcedMode ?? 'category');

  // When forcedMode is set, it overrides the user's toggle selection.
  const activeMode = forcedMode ?? mode;
  const isCategoryMode = activeMode === 'category';

  const chartData = isCategoryMode
    ? categoryAllocation.items.map((item) => ({
        name: tCommon(`categories.${item.category}`),
        value: item.value,
        percentage: item.percentage,
        targetPercentage: null as number | null,
        difference: null as number | null,
      }))
    : groupAllocation.items.map((item) => ({
        name: item.groupName === UNGROUPED_LABEL ? t('distribution.ungrouped') : item.groupName,
        value: item.value,
        percentage: item.percentage,
        targetPercentage: item.targetPercentage,
        difference: item.difference,
      }));

  const hasData = chartData.length > 0;
  const hasTargets = !isCategoryMode && chartData.some((e) => e.targetPercentage != null);

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
        {!forcedMode && (
          <PillToggleGroup
            items={[
              { value: 'category', label: t('distribution.byCategory') },
              { value: 'group', label: t('distribution.byGroup') },
            ]}
            value={mode}
            onValueChange={(v) => setMode(v as Mode)}
          />
        )}
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
                <div className="w-full lg:flex-1 lg:min-w-0">
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                      key={activeMode}
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
                            {fmt.pct(entry.percentage)}%
                          </span>
                          {entry.targetPercentage != null && (
                            <span
                              className={`shrink-0 text-paragraph-mini ${
                                entry.difference != null && entry.difference > 0
                                  ? 'text-red-500'
                                  : entry.difference != null && entry.difference < 0
                                    ? 'text-amber-500'
                                    : 'text-muted-foreground'
                              }`}
                            >
                              ({fmt.pct(entry.targetPercentage)}%)
                            </span>
                          )}
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
                  <ResponsiveContainer key={activeMode} width="100%" height="100%">
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
                        formatter={(value) => fmt.value(Number(value), { compact: true })}
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

              {/* Target color legend — only when groups have targets. */}
              <AnimatePresence initial={false}>
                {hasTargets && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: ANIMATION_DEFAULT }}
                    className="flex items-center justify-center gap-x-4 text-paragraph-xs text-muted-foreground"
                  >
                    <span>
                      <span className="text-red-500">●</span> {t('distribution.overAllocated')}
                    </span>
                    <span>
                      <span className="text-amber-500">●</span> {t('distribution.underAllocated')}
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
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
