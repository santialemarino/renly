'use client';

import { useLocale, useTranslations } from 'next-intl';

import { SampleDataTable, type SampleColumn } from '@/components/sample/sample-data-table';
import type { Expense } from '@/lib/api/expenses';
import { sampleExpenses } from '@/lib/sample-data';
import { formatAmount } from '@/lib/utils/currency';
import { formatDateForLocale } from '@/lib/utils/format';

// First-run sample expenses: mirrors the real table's columns, but reads from the client fixture.
export function SampleExpensesTable() {
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  const columns: SampleColumn<Expense>[] = [
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
    {
      header: t('table.paymentMethod'),
      cell: (e) => (e.paymentMethod ? t(`paymentMethods.${e.paymentMethod}`) : '—'),
    },
    { header: t('table.notes'), cell: (e) => e.notes ?? '—' },
  ];

  const getDetail = (e: Expense) => ({
    title: e.category ? tCommon(`categories.${e.category}`) : formatDateForLocale(e.date, locale),
    fields: [
      { label: t('table.date'), value: formatDateForLocale(e.date, locale) },
      { label: t('table.amount'), value: formatAmount(e.amount, locale, e.currency) },
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
