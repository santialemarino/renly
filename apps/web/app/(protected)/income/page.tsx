import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { IncomeDataTable } from '@/app/(protected)/income/_components/income-data-table';
import { IncomeToolbar } from '@/app/(protected)/income/_components/income-toolbar';
import { SampleIncomeTable } from '@/app/(protected)/income/_components/sample-income-table';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { getIncome } from '@/lib/api/income';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
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
  const cookieStore = await cookies();

  const settings = await getSettings().catch(() => null);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const activeCurrency = savedCurrency || primary;
  const currency = activeCurrency !== ORIGINAL_CURRENCY ? activeCurrency : undefined;

  const data = await getIncome({
    search: params.search,
    category: params.category,
    dateFrom: params.date_from,
    dateTo: params.date_to,
    currency,
    page: params.page ? Number(params.page) : 1,
    sortBy: params.sort_by as 'date' | 'amount' | 'category' | undefined,
    sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
  });

  // Show this section's first-run sample only while it's empty; fetch the flag just then so a
  // populated section never pays for the extra read.
  const showSample =
    data.items.length === 0
      ? ((await getOnboardingStatus().catch(() => null))?.sampleIncome ?? false)
      : false;

  // Once the sample is retired, a still-onboarding user gets the teaching empty state (the fallback
  // that keeps this page consistent with the other list pages); a filtered-empty view stays plain.
  const hasActiveFilters =
    !!params.search || !!params.category || !!params.date_from || !!params.date_to;
  const firstRun = isFirstRunEmptyState(data.items.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <DismissableCurrencyHint show={!!currency} />
      <IncomeToolbar preferredCurrencies={preferredCurrencies} />
      {showSample ? (
        <SampleIncomeTable />
      ) : (
        <IncomeDataTable
          data={data}
          preferredCurrencies={preferredCurrencies}
          activeCurrency={currency}
          firstRun={firstRun}
        />
      )}
    </div>
  );
}
