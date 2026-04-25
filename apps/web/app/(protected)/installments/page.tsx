import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { InstallmentsTable } from '@/app/(protected)/installments/_components/installments-table';
import { InstallmentsToolbar } from '@/app/(protected)/installments/_components/installments-toolbar';
import { getCreditCards } from '@/lib/api/credit-cards';
import { getInstallments, type InstallmentSortField, type SortOrder } from '@/lib/api/installments';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
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

  const [settings, creditCards] = await Promise.all([
    getSettings().catch(() => null),
    getCreditCards().catch(() => []),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const activeCurrency = savedCurrency || primary;
  const currency = activeCurrency !== ORIGINAL_CURRENCY ? activeCurrency : undefined;

  const installments = await getInstallments({
    search: params.search,
    sortBy: params.sort_by as InstallmentSortField | undefined,
    sortOrder: params.sort_order as SortOrder | undefined,
    showArchived: params.show_archived === 'true',
    currency,
  });

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <InstallmentsToolbar preferredCurrencies={preferredCurrencies} creditCards={creditCards} />
      <InstallmentsTable
        installments={installments}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
      />
    </div>
  );
}
