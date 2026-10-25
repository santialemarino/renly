'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { DistributionDonut } from '@/app/(protected)/_components/distribution-donut';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import type { AllocationResponse, CollectionAllocationResponse } from '@/lib/api/metrics';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { UNASSIGNED_LABEL } from '@/lib/constants/api-constants';
import { useFormatters } from '@/lib/i18n/formatters';

type Mode = 'category' | 'collection';

interface InvestorDashboardDistributionProps {
  categoryAllocation: AllocationResponse;
  collectionAllocation: CollectionAllocationResponse;
  forcedMode?: Mode;
}

export function InvestorDashboardDistribution({
  categoryAllocation,
  collectionAllocation,
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
    : collectionAllocation.items.map((item) => ({
        name:
          item.collectionName === UNASSIGNED_LABEL
            ? t('distribution.unassigned')
            : item.collectionName,
        value: item.value,
        percentage: item.percentage,
        targetPercentage: item.targetPercentage,
        difference: item.difference,
      }));

  const hasTargets = !isCategoryMode && chartData.some((e) => e.targetPercentage != null);

  // A collection with a target shows it after its share, coloured by which side of it the share is.
  const slices = chartData.map((entry) => ({
    name: entry.name,
    value: entry.value,
    percentage: entry.percentage,
    extra: entry.targetPercentage != null && (
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
    ),
  }));

  return (
    <DistributionDonut
      title={t('distribution.title')}
      slices={slices}
      dataKey={activeMode}
      emptyLabel={t('noData')}
      toggle={
        !forcedMode && (
          <PillToggleGroup
            items={[
              { value: 'category', label: t('distribution.byCategory') },
              { value: 'collection', label: t('distribution.byCollection') },
            ]}
            value={mode}
            onValueChange={(v) => setMode(v as Mode)}
          />
        )
      }
      footer={
        /* Target color legend — only when collections have targets. */
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
      }
    />
  );
}
