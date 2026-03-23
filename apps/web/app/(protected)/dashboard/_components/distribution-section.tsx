'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ToggleGroup,
  ToggleGroupItem,
} from '@repo/ui/components';
import type { AllocationResponse, GroupAllocationResponse } from '@/lib/api/metrics';
import {
  CHART_ANIMATION_DURATION,
  CHART_ANIMATION_EASING,
  DONUT_COLORS,
  DONUT_HEIGHT,
  DONUT_INNER_RADIUS,
  DONUT_OUTER_RADIUS,
  DONUT_PADDING_ANGLE,
  FORMAT_THRESHOLD_MILLION,
  FORMAT_THRESHOLD_THOUSAND,
  TOOLTIP_ANIMATION_DURATION,
  TOOLTIP_BG,
  TOOLTIP_BORDER,
  TOOLTIP_BORDER_RADIUS,
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
} from '@/lib/constants/charts';
import { UNGROUPED_LABEL } from '@/lib/constants/db-constraints';

type Mode = 'category' | 'group';

// Formats a number as a compact value.
function formatValue(value: number): string {
  if (value >= FORMAT_THRESHOLD_MILLION) return `${(value / FORMAT_THRESHOLD_MILLION).toFixed(1)}M`;
  if (value >= FORMAT_THRESHOLD_THOUSAND)
    return `${(value / FORMAT_THRESHOLD_THOUSAND).toFixed(0)}K`;
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(value);
}

interface DistributionSectionProps {
  categoryAllocation: AllocationResponse;
  groupAllocation: GroupAllocationResponse;
  forcedMode?: Mode;
}

export function DistributionSection({
  categoryAllocation,
  groupAllocation,
  forcedMode,
}: DistributionSectionProps) {
  const t = useTranslations('dashboard');
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
      }))
    : groupAllocation.items.map((item) => ({
        name: item.groupName === UNGROUPED_LABEL ? t('distribution.ungrouped') : item.groupName,
        value: item.value,
        percentage: item.percentage,
      }));

  const hasData = chartData.length > 0;

  return (
    <Card className="flex-1">
      <CardHeader className="flex flex-row items-center justify-between px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('distribution.title')}
        </CardTitle>
        {!forcedMode && (
          <ToggleGroup
            type="single"
            value={mode}
            onValueChange={(v) => {
              if (v) setMode(v as Mode);
            }}
            variant="outline"
            size="sm"
            className="border border-border bg-white rounded-full overflow-hidden shadow-xs"
          >
            <ToggleGroupItem
              value="category"
              className="border-0 data-[state=on]:bg-blue-800 data-[state=on]:text-white transition-all duration-200 focus-visible:outline-none focus-visible:bg-accent focus-visible:animate-[pulse-scale_0.3s_ease-in-out]"
            >
              {t('distribution.byCategory')}
            </ToggleGroupItem>
            <ToggleGroupItem
              value="group"
              className="border-0 data-[state=on]:bg-blue-800 data-[state=on]:text-white transition-all duration-200 focus-visible:outline-none focus-visible:bg-accent focus-visible:animate-[pulse-scale_0.3s_ease-in-out]"
            >
              {t('distribution.byGroup')}
            </ToggleGroupItem>
          </ToggleGroup>
        )}
      </CardHeader>
      <CardContent className="px-6 pb-6">
        {hasData ? (
          <div className="flex flex-col items-center gap-y-4">
            <div style={{ height: DONUT_HEIGHT }} className="w-full">
              <ResponsiveContainer width="100%" height="100%">
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
                    formatter={(value) => formatValue(Number(value))}
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

            {/* Legend */}
            <div className="grid w-full grid-cols-2 gap-x-4 gap-y-2">
              {chartData.map((entry, index) => (
                <div key={entry.name} className="flex items-center gap-x-2">
                  <div
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: DONUT_COLORS[index % DONUT_COLORS.length] }}
                  />
                  <span className="min-w-0 truncate text-paragraph-mini text-muted-foreground">
                    {entry.name}
                  </span>
                  <span className="shrink-0 ml-auto text-paragraph-mini-semibold">
                    {entry.percentage.toFixed(1)}%
                  </span>
                </div>
              ))}
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
