import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PaymentObligationsTable } from '@/app/(protected)/payment-obligations/_components/payment-obligations-table';
import { PaymentObligationsToolbar } from '@/app/(protected)/payment-obligations/_components/payment-obligations-toolbar';
import { getCreditCards } from '@/lib/api/credit-cards';
import {
  getPaymentObligations,
  type PaymentObligationSortField,
  type SortOrder,
} from '@/lib/api/payment-obligations';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
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

  const [settings, creditCards] = await Promise.all([
    getSettings().catch(() => null),
    getCreditCards().catch(() => []),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const activeCurrency = savedCurrency || primary;
  const currency = activeCurrency !== ORIGINAL_CURRENCY ? activeCurrency : undefined;

  const obligations = await getPaymentObligations({
    search: params.search,
    sortBy: params.sort_by as PaymentObligationSortField | undefined,
    sortOrder: params.sort_order as SortOrder | undefined,
    showArchived: params.show_archived === 'true',
    currency,
  });

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
        creditCards={creditCards}
      />
    </div>
  );
}
