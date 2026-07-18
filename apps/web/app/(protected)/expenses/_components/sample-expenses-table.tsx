'use client';

import { useTranslations } from 'next-intl';

import { SampleDataTable, type SampleColumn } from '@/components/sample/sample-data-table';
import type { Expense } from '@/lib/api/expenses';
import { useFormatters } from '@/lib/i18n/formatters';
import { sampleExpenses } from '@/lib/sample-data';

// First-run sample expenses: mirrors the real table's columns, but reads from the client fixture.
export function SampleExpensesTable() {
  const fmt = useFormatters();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  const columns: SampleColumn<Expense>[] = [
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
    {
      header: t('table.paymentMethod'),
      cell: (e) => (e.paymentMethod ? t(`paymentMethods.${e.paymentMethod}`) : '—'),
    },
    { header: t('table.notes'), cell: (e) => e.notes ?? '—' },
  ];

  const getDetail = (e: Expense) => ({
    title: e.category ? tCommon(`categories.${e.category}`) : fmt.date(e.date),
    fields: [
      { label: t('table.date'), value: fmt.date(e.date) },
      { label: t('table.amount'), value: fmt.amount(e.amount, e.currency) },
      { label: t('table.category'), value: e.category ? tCommon(`categories.${e.category}`) : '—' },
      {
        label: t('table.paymentMethod'),
        value: e.paymentMethod ? t(`paymentMethods.${e.paymentMethod}`) : '—',
      },
      { label: t('table.notes'), value: e.notes ?? '—' },
    ],
  });

  return (
    <SampleDataTable
      entity="expenses"
      columns={columns}
      rows={sampleExpenses}
      getDetail={getDetail}
    />
  );
}
