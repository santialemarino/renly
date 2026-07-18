'use client';

import { useTranslations } from 'next-intl';

import { SampleDataTable, type SampleColumn } from '@/components/sample/sample-data-table';
import type { IncomeEntry } from '@/lib/api/income';
import { useFormatters } from '@/lib/i18n/formatters';
import { sampleIncome } from '@/lib/sample-data';

// First-run sample income: mirrors the real table's columns, but reads from the client fixture.
export function SampleIncomeTable() {
  const fmt = useFormatters();
  const t = useTranslations('income');
  const tCommon = useTranslations('common');

  const columns: SampleColumn<IncomeEntry>[] = [
    { header: t('table.date'), cell: (e) => fmt.date(e.date) },
    {
      header: t('table.amount'),
      cell: (e) => fmt.amount(e.amount, e.currency),
      className: 'tabular-nums',
    },
    {
      header: t('table.category'),
      cell: (e) => (e.category ? tCommon(`categories.${e.category}`) : '—'),
    },
    { header: t('table.notes'), cell: (e) => e.notes ?? '—' },
  ];

  const getDetail = (e: IncomeEntry) => ({
    title: e.category ? tCommon(`categories.${e.category}`) : fmt.date(e.date),
    fields: [
      { label: t('table.date'), value: fmt.date(e.date) },
      { label: t('table.amount'), value: fmt.amount(e.amount, e.currency) },
      { label: t('table.category'), value: e.category ? tCommon(`categories.${e.category}`) : '—' },
      { label: t('table.notes'), value: e.notes ?? '—' },
    ],
  });

  return (
    <SampleDataTable entity="income" columns={columns} rows={sampleIncome} getDetail={getDetail} />
  );
}
