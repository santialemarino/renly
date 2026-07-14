'use client';

import { useLocale, useTranslations } from 'next-intl';

import { SampleDataTable, type SampleColumn } from '@/components/sample/sample-data-table';
import type { IncomeEntry } from '@/lib/api/income';
import { sampleIncome } from '@/lib/sample-data';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

// First-run sample income: mirrors the real table's columns, but reads from the client fixture.
export function SampleIncomeTable() {
  const locale = useLocale();
  const t = useTranslations('income');
  const tCommon = useTranslations('common');

  const columns: SampleColumn<IncomeEntry>[] = [
    { header: t('table.date'), cell: (e) => formatDateForLocale(e.date, locale) },
    {
      header: t('table.amount'),
      cell: (e) => formatAmount(e.amount, locale, e.currency),
      className: 'tabular-nums',
    },
    {
      header: t('table.category'),
      cell: (e) => (e.category ? tCommon(`categories.${e.category}`) : '—'),
    },
    { header: t('table.notes'), cell: (e) => e.notes ?? '—' },
  ];

  const getDetail = (e: IncomeEntry) => ({
    title: e.category ? tCommon(`categories.${e.category}`) : formatDateForLocale(e.date, locale),
    fields: [
      { label: t('table.date'), value: formatDateForLocale(e.date, locale) },
      { label: t('table.amount'), value: formatAmount(e.amount, locale, e.currency) },
      { label: t('table.category'), value: e.category ? tCommon(`categories.${e.category}`) : '—' },
      { label: t('table.notes'), value: e.notes ?? '—' },
    ],
  });

  return (
    <SampleDataTable entity="income" columns={columns} rows={sampleIncome} getDetail={getDetail} />
  );
}
