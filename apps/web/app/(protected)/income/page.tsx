import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { IncomeDataTable } from '@/app/(protected)/income/_components/income-data-table';
import { IncomeToolbar } from '@/app/(protected)/income/_components/income-toolbar';
import { SampleIncomeTable } from '@/app/(protected)/income/_components/sample-income-table';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { getAccounts } from '@/lib/api/accounts';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getGroups } from '@/lib/api/groups';
import { getIncome } from '@/lib/api/income';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
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
  // Entry forms restrict their currency picker to the convertible set; on a fetch error the
  // picker degrades to the full list and the API's 422 still guards.
  const supportedCurrencies = await getSupportedCurrencies().catch(() => undefined);
  /*
   * Accounts for the optional "deposited to" link (empty on error → the field hides itself). Archived
   * ones are included so an entry linked to a since-archived account still renders it by name instead
   * of a blank picker; the picker only ever OFFERS active accounts.
   */
  const accounts = await getAccounts({ showArchived: true }).catch(() => []);
  /*
   * The groups the user belongs to, which is what turns the entry form's scope control on. Empty on a
   * fetch error, and the control then simply does not render — a solo user's experience, which is the
   * right degradation: the private form still works and the API still refuses joint money.
   */
  const groups = await getGroups().catch(() => []);

  const currency = resolveActiveCurrency(cookieStore, primary);

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
      <IncomeToolbar
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={accounts}
        groups={groups}
        timeZone={settings?.timezone ?? undefined}
      />
      {showSample ? (
        <SampleIncomeTable />
      ) : (
        <IncomeDataTable
          data={data}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          accounts={accounts}
          activeCurrency={currency}
          firstRun={firstRun}
        />
      )}
    </div>
  );
}
