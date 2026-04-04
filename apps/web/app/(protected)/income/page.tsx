import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { IncomeDataTable } from '@/app/(protected)/income/_components/income-data-table';
import { IncomeToolbar } from '@/app/(protected)/income/_components/income-toolbar';
import { getIncome } from '@/lib/api/income';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('income');
}

interface IncomePageProps {
  searchParams: Promise<{
    search?: string;
    category?: string;
    date_from?: string;
    date_to?: string;
    page?: string;
    sort_by?: string;
    sort_order?: string;
  }>;
}

export default async function IncomePage({ searchParams }: IncomePageProps) {
  const t = await getTranslations('income');
  const params = await searchParams;

  const [data, settings] = await Promise.all([
    getIncome({
      search: params.search,
      category: params.category,
      dateFrom: params.date_from,
      dateTo: params.date_to,
      page: params.page ? Number(params.page) : 1,
      sortBy: params.sort_by as 'date' | 'amount' | 'category' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getSettings().catch(() => null),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <IncomeToolbar preferredCurrencies={preferredCurrencies} />
      <IncomeDataTable data={data} preferredCurrencies={preferredCurrencies} />
    </div>
  );
}
