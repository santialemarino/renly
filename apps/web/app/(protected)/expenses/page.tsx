import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { ExpensesDataTable } from '@/app/(protected)/expenses/_components/expenses-data-table';
import { ExpensesToolbar } from '@/app/(protected)/expenses/_components/expenses-toolbar';
import { SampleExpensesTable } from '@/app/(protected)/expenses/_components/sample-expenses-table';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { getCreditCards } from '@/lib/api/credit-cards';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getExpenses } from '@/lib/api/expenses';
import { getInstallments } from '@/lib/api/installments';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getPaymentObligations } from '@/lib/api/payment-obligations';
import { getSettings } from '@/lib/api/settings';
import { getSubscriptions } from '@/lib/api/subscriptions';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
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
  const cookieStore = await cookies();

  const [settings, creditCards, supportedCurrencies] = await Promise.all([
    getSettings().catch(() => null),
    getCreditCards().catch(() => []),
    // Entry forms restrict their currency picker to the convertible set; on a fetch error the
    // picker degrades to the full list and the API's 422 still guards.
    getSupportedCurrencies().catch(() => undefined),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const activeCurrency = savedCurrency || primary;
  const currency = activeCurrency !== ORIGINAL_CURRENCY ? activeCurrency : undefined;

  const data = await getExpenses({
    search: params.search,
    category: params.category,
    paymentMethod: params.payment_method,
    dateFrom: params.date_from,
    dateTo: params.date_to,
    currency,
    page: params.page ? Number(params.page) : 1,
    sortBy: params.sort_by as 'date' | 'amount' | 'category' | 'payment_method' | undefined,
    sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
  });

  // Show this section's first-run sample only while it's empty; fetch the flag just then so a
  // populated section never pays for the extra read.
  const showSample =
    data.items.length === 0
      ? ((await getOnboardingStatus().catch(() => null))?.sampleExpenses ?? false)
      : false;

  // Once the sample is retired, a still-onboarding user gets the teaching empty state (the fallback
  // that keeps this page consistent with the other list pages); a filtered-empty view stays plain.
  const hasActiveFilters =
    !!params.search ||
    !!params.category ||
    !!params.payment_method ||
    !!params.date_from ||
    !!params.date_to;
  const firstRun = isFirstRunEmptyState(data.items.length === 0, hasActiveFilters, settings);

  // Collect linked-plan ids from the loaded page so the edit dropdowns can still render
  // the plan name when an expense links to a since-archived plan (Phase 3 audit-round-3
  // follow-up). Backend's `include_ids` widens the active-only listing with these specific
  // archived rows; active plans not in include_ids are unaffected.
  const linkedObligationIds = Array.from(
    new Set(data.items.map((e) => e.paymentObligationId).filter((x): x is number => x !== null)),
  );
  const linkedSubscriptionIds = Array.from(
    new Set(data.items.map((e) => e.subscriptionId).filter((x): x is number => x !== null)),
  );
  const linkedInstallmentIds = Array.from(
    new Set(data.items.map((e) => e.installmentId).filter((x): x is number => x !== null)),
  );

  const [activeObligations, activeSubscriptions, activeInstallments] = await Promise.all([
    getPaymentObligations({ showArchived: false, includeIds: linkedObligationIds }).catch(() => []),
    getSubscriptions({ showArchived: false, includeIds: linkedSubscriptionIds }).catch(() => []),
    getInstallments({ showArchived: false, includeIds: linkedInstallmentIds }).catch(() => []),
  ]);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <DismissableCurrencyHint show={!!currency} />
      <ExpensesToolbar
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={activeObligations}
        activeSubscriptions={activeSubscriptions}
        activeInstallments={activeInstallments}
      />
      {showSample ? (
        <SampleExpensesTable />
      ) : (
        <ExpensesDataTable
          data={data}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          creditCards={creditCards}
          activeObligations={activeObligations}
          activeSubscriptions={activeSubscriptions}
          activeInstallments={activeInstallments}
          activeCurrency={currency}
          firstRun={firstRun}
        />
      )}
    </div>
  );
}
