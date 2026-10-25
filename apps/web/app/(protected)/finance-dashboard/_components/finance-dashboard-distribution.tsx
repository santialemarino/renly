'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';

import { DistributionDonut } from '@/app/(protected)/_components/distribution-donut';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import type { ExpenseBreakdown, IncomeBreakdown } from '@/lib/api/finance-metrics';

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
  const tCommon = useTranslations('common');
  const [mode, setMode] = useState<Mode>('expense');

  // A category can be negative (a card credit posts a negative reconciliation adjustment). A pie
  // slice cannot represent one, and the API already zeroes its percentage, so drop it from the
  // chart — the headline totals elsewhere still carry it, so no money disappears from the page.
  const slices = (mode === 'expense' ? expenseBreakdown.items : incomeBreakdown.items)
    .filter((item) => item.value > 0)
    .map((item) => ({
      name: tCommon(`categories.${item.category}`),
      value: item.value,
      percentage: item.percentage,
    }));

  return (
    <DistributionDonut
      title={t('distribution.title')}
      slices={slices}
      dataKey={mode}
      emptyLabel={t('noData')}
      toggle={
        <PillToggleGroup
          items={[
            { value: 'expense', label: t('distribution.byExpense') },
            { value: 'income', label: t('distribution.byIncome') },
          ]}
          value={mode}
          onValueChange={(v) => setMode(v as Mode)}
        />
      }
    />
  );
}
