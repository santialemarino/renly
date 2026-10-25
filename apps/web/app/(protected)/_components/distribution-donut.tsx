'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@repo/ui/components';
import { DonutLegend, DonutLegendLayout } from '@/components/donut-legend';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import {
  CHART_ANIMATION_DURATION,
  CHART_ANIMATION_EASING,
  DONUT_COLORS,
  DONUT_HEIGHT,
  DONUT_INNER_RADIUS,
  DONUT_OUTER_RADIUS,
  DONUT_PADDING_ANGLE,
  DONUT_STROKE_WIDTH,
  TOOLTIP_ANIMATION_DURATION,
  TOOLTIP_BG,
  TOOLTIP_BORDER,
  TOOLTIP_BORDER_RADIUS,
  TOOLTIP_FONT_SIZE,
  TOOLTIP_TEXT,
} from '@/lib/constants/charts';
import { useFormatters } from '@/lib/i18n/formatters';

export interface DistributionSlice {
  name: string;
  value: number;
  // Already in percent units (40 → "40%").
  percentage: number;
  // Anything the legend shows after the percentage, e.g. a collection's target.
  extra?: ReactNode;
}

interface DistributionDonutProps {
  title: string;
  slices: DistributionSlice[];
  // Names the data set on screen. A change remounts the chart (Recharts replays its draw) and fades
  // the legend, so a mode switch reads as a new set rather than slices morphing into others.
  dataKey: string;
  emptyLabel: string;
  // The header's control, e.g. the mode toggle.
  toggle?: ReactNode;
  // Below the chart and legend, inside the animated height, e.g. a key to the legend's colours.
  footer?: ReactNode;
}

/*
 * A dashboard's distribution card: a donut beside its legend, switched between data sets by the
 * caller's toggle. The card animates its height to the legend's, so a set with more rows grows the
 * card instead of jumping it.
 */
export function DistributionDonut({
  title,
  slices,
  dataKey,
  emptyLabel,
  toggle,
  footer,
}: DistributionDonutProps) {
  const fmt = useFormatters();
  const legendRef = useRef<HTMLDivElement>(null);
  const [legendHeight, setLegendHeight] = useState<number>(0);
  const initialized = useRef(false);

  const hasData = slices.length > 0;

  // Measure legend height for smooth bottom-edge animation. The legend only exists while there is
  // data, so the measuring follows `hasData`: a card that opens on its empty label and then switches
  // to a set with data must measure the legend that just mounted, or it stays at height 0.
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
  }, [hasData]);

  return (
    <Card className="flex-1">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">{title}</CardTitle>
        {toggle}
      </CardHeader>
      <CardContent className="px-6">
        {hasData ? (
          <div
            className="overflow-hidden transition-[height] duration-300 ease-in-out"
            style={{ height: legendHeight }}
          >
            <div ref={legendRef} className="flex flex-col gap-y-4">
              {/* Chart (top in a narrow card, right in a wide one) + Legend */}
              <DonutLegendLayout
                legend={
                  /* Legend items — content fades on mode switch. */
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                      key={dataKey}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: ANIMATION_DEFAULT }}
                    >
                      <DonutLegend
                        items={slices.map((slice, index) => ({
                          key: slice.name,
                          name: slice.name,
                          color: DONUT_COLORS[index % DONUT_COLORS.length],
                          percentage: slice.percentage,
                          extra: slice.extra,
                        }))}
                      />
                    </motion.div>
                  </AnimatePresence>
                }
                chart={
                  /* Donut chart — key forces remount so Recharts replays the draw animation. */
                  <div
                    style={{ height: DONUT_HEIGHT, maxWidth: DONUT_HEIGHT }}
                    className="w-full shrink-0"
                  >
                    <ResponsiveContainer key={dataKey} width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={slices}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={DONUT_INNER_RADIUS}
                          outerRadius={DONUT_OUTER_RADIUS}
                          animationDuration={CHART_ANIMATION_DURATION}
                          animationEasing={CHART_ANIMATION_EASING}
                          paddingAngle={DONUT_PADDING_ANGLE}
                          strokeWidth={DONUT_STROKE_WIDTH}
                        >
                          {slices.map((_slice, index) => (
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
                }
              />
              {footer}
            </div>
          </div>
        ) : (
          <div style={{ height: DONUT_HEIGHT }} className="flex items-center justify-center">
            <p className="text-paragraph-sm text-muted-foreground">{emptyLabel}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
