import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { ExpensesDataTable } from '@/app/(protected)/expenses/_components/expenses-data-table';
import { ExpensesToolbar } from '@/app/(protected)/expenses/_components/expenses-toolbar';
import { getExpenses } from '@/lib/api/expenses';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('expenses');
}

interface ExpensesPageProps {
  searchParams: Promise<{
    search?: string;
    category?: string;
    payment_method?: string;
    date_from?: string;
    date_to?: string;
    page?: string;
    sort_by?: string;
    sort_order?: string;
  }>;
}

export default async function ExpensesPage({ searchParams }: ExpensesPageProps) {
  const t = await getTranslations('expenses');
  const params = await searchParams;

  const [data, settings] = await Promise.all([
    getExpenses({
      search: params.search,
      category: params.category,
      paymentMethod: params.payment_method,
      dateFrom: params.date_from,
      dateTo: params.date_to,
      page: params.page ? Number(params.page) : 1,
      sortBy: params.sort_by as 'date' | 'amount' | 'category' | 'payment_method' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getSettings().catch(() => null),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <ExpensesToolbar preferredCurrencies={preferredCurrencies} />
      <ExpensesDataTable data={data} preferredCurrencies={preferredCurrencies} />
    </div>
  );
}
