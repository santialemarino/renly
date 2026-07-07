'use client';

import { useTranslations } from 'next-intl';

import { SampleDataTable, type SampleColumn } from '@/components/sample/sample-data-table';
import type { Investment } from '@/lib/api/investments';
import { sampleInvestments } from '@/lib/sample-data';

// First-run sample investments: mirrors the real table's columns, but reads from the client fixture.
export function SampleInvestmentsTable() {
  const t = useTranslations('investments');
  const tCommon = useTranslations('common');

  const columns: SampleColumn<Investment>[] = [
    { header: t('table.name'), cell: (i) => i.name },
    { header: t('table.category'), cell: (i) => tCommon(`categories.${i.category}`) },
    { header: t('table.ticker'), cell: (i) => i.ticker ?? '—' },
    { header: t('table.currency'), cell: (i) => i.baseCurrency },
    { header: t('table.broker'), cell: (i) => i.broker ?? '—' },
  ];

  const getDetail = (i: Investment) => ({
    title: i.name,
    fields: [
      { label: t('table.category'), value: tCommon(`categories.${i.category}`) },
      { label: t('table.ticker'), value: i.ticker ?? '—' },
      { label: t('table.currency'), value: i.baseCurrency },
      { label: t('table.broker'), value: i.broker ?? '—' },
    ],
  });

  return (
    <SampleDataTable
      entity="investments"
      columns={columns}
      rows={sampleInvestments}
      getDetail={getDetail}
    />
  );
}
