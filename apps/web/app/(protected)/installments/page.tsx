import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { InstallmentsTable } from '@/app/(protected)/installments/_components/installments-table';
import { InstallmentsToolbar } from '@/app/(protected)/installments/_components/installments-toolbar';
import { getInstallments, type InstallmentSortField } from '@/lib/api/installments';
import { getPageSettings } from '@/lib/api/settings';
import type { SortOrder } from '@/lib/api/types';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('installments');
}

interface InstallmentsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function InstallmentsPage({ searchParams }: InstallmentsPageProps) {
  const t = await getTranslations('installments');
  const params = await searchParams;
  const cookieStore = await cookies();

  const { settings, creditCards } = await getPageSettings();
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const currency = resolveActiveCurrency(cookieStore, primary);

  const installments = await getInstallments({
    search: params.search,
    sortBy: params.sort_by as InstallmentSortField | undefined,
    sortOrder: params.sort_order as SortOrder | undefined,
    showArchived: params.show_archived === 'true',
    currency,
  });

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun = isFirstRunEmptyState(installments.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <InstallmentsToolbar preferredCurrencies={preferredCurrencies} creditCards={creditCards} />
      <InstallmentsTable
        installments={installments}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        activeCurrency={currency}
        firstRun={firstRun}
      />
    </div>
  );
}
