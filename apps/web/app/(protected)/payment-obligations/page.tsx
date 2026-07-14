import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PaymentObligationsTable } from '@/app/(protected)/payment-obligations/_components/payment-obligations-table';
import { PaymentObligationsToolbar } from '@/app/(protected)/payment-obligations/_components/payment-obligations-toolbar';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import {
  getPaymentObligations,
  type PaymentObligationSortField,
} from '@/lib/api/payment-obligations';
import { getPageSettings } from '@/lib/api/settings';
import type { SortOrder } from '@/lib/api/types';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('paymentObligations');
}

interface PaymentObligationsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function PaymentObligationsPage({
  searchParams,
}: PaymentObligationsPageProps) {
  const t = await getTranslations('paymentObligations');
  const params = await searchParams;
  const cookieStore = await cookies();

  const [{ settings, creditCards }, supportedCurrencies] = await Promise.all([
    getPageSettings(),
    // The Mark-Paid expense dialog restricts its currency picker to the convertible set; on a
    // fetch error the picker degrades to the full list and the API's 422 still guards.
    getSupportedCurrencies().catch(() => undefined),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const currency = resolveActiveCurrency(cookieStore, primary);

  const obligations = await getPaymentObligations({
    search: params.search,
    sortBy: params.sort_by as PaymentObligationSortField | undefined,
    sortOrder: params.sort_order as SortOrder | undefined,
    showArchived: params.show_archived === 'true',
    currency,
  });

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun = isFirstRunEmptyState(obligations.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <PaymentObligationsToolbar
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
      />
      <PaymentObligationsTable
        obligations={obligations}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeCurrency={currency}
        firstRun={firstRun}
      />
    </div>
  );
}
