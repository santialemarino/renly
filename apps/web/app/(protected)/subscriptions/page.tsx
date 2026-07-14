import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { SubscriptionsTable } from '@/app/(protected)/subscriptions/_components/subscriptions-table';
import { SubscriptionsToolbar } from '@/app/(protected)/subscriptions/_components/subscriptions-toolbar';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getPageSettings } from '@/lib/api/settings';
import { getSubscriptions, type SubscriptionSortField } from '@/lib/api/subscriptions';
import type { SortOrder } from '@/lib/api/types';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('subscriptions');
}

interface SubscriptionsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function SubscriptionsPage({ searchParams }: SubscriptionsPageProps) {
  const t = await getTranslations('subscriptions');
  const params = await searchParams;
  const cookieStore = await cookies();

  const [{ settings, creditCards }, supportedCurrencies] = await Promise.all([
    getPageSettings(),
    // Entry forms restrict their currency picker to the convertible set; on a fetch error the
    // picker degrades to the full list and the API's 422 still guards.
    getSupportedCurrencies().catch(() => undefined),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const currency = resolveActiveCurrency(cookieStore, primary);

  const subscriptions = await getSubscriptions({
    search: params.search,
    sortBy: params.sort_by as SubscriptionSortField | undefined,
    sortOrder: params.sort_order as SortOrder | undefined,
    showArchived: params.show_archived === 'true',
    currency,
  });

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun = isFirstRunEmptyState(subscriptions.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <SubscriptionsToolbar
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
      />
      <SubscriptionsTable
        subscriptions={subscriptions}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeCurrency={currency}
        firstRun={firstRun}
      />
    </div>
  );
}
