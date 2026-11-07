import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { IncomeDataTable } from '@/app/(protected)/income/_components/income-data-table';
import { IncomeToolbar } from '@/app/(protected)/income/_components/income-toolbar';
import { SampleIncomeTable } from '@/app/(protected)/income/_components/sample-income-table';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { WarningHint } from '@/components/styled-hint';
import { getAccounts } from '@/lib/api/accounts';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getGroups } from '@/lib/api/groups';
import { getIncome } from '@/lib/api/income';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { getFormatters } from '@/lib/i18n/formatters-server';
import { resolveListScope, resolvePageParam } from '@/lib/list-scope';
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
    scope?: string;
  }>;
}

export default async function IncomePage({ searchParams }: IncomePageProps) {
  const fmt = await getFormatters();
  const t = await getTranslations('income');
  const params = await searchParams;
  const cookieStore = await cookies();

  const scope = resolveListScope(params.scope);

  /*
   * All at once, bar one: the table waits only for the settings it is priced in (request-memoized,
   * shared with the layout on a full load), and the first-run sample flag only for the table — it
   * is read only when the table is empty, so a populated section never pays for it. Everything else
   * starts at once.
   */
  const settingsRead = getSettings().catch(() => null);
  const incomeRead = settingsRead.then((pageSettings) =>
    getIncome({
      scope,
      search: params.search,
      category: params.category,
      dateFrom: params.date_from,
      dateTo: params.date_to,
      currency: resolveActiveCurrency(
        cookieStore,
        pageSettings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY,
      ),
      page: resolvePageParam(params.page),
      sortBy: params.sort_by as 'date' | 'amount' | 'category' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
  );
  const [settings, supportedCurrencies, accounts, groups, data, showSample] = await Promise.all([
    settingsRead,
    // Entry forms restrict their currency picker to the convertible set; on a fetch error the
    // picker degrades to the full list and the API's 422 still guards.
    getSupportedCurrencies().catch(() => undefined),
    /*
     * Accounts for the optional "deposited to" link (empty on error → the field hides itself). Archived
     * ones are included so an entry linked to a since-archived account still renders it by name
     * instead of a blank picker; the picker only ever OFFERS active accounts.
     */
    getAccounts({ showArchived: true }).catch(() => []),
    /*
     * The groups the user belongs to, which is what turns the entry form's scope control on. Empty on
     * a fetch error, and the control then simply does not render — a solo user's experience, which is
     * the right degradation: the private form still works and the API still refuses joint money.
     */
    getGroups().catch(() => []),
    incomeRead,
    incomeRead.then(async (income) =>
      income.items.length === 0
        ? ((await getOnboardingStatus().catch(() => null))?.sampleIncome ?? false)
        : false,
    ),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;
  const currency = resolveActiveCurrency(cookieStore, primary);

  // Once the sample is retired, a still-onboarding user gets the teaching empty state (the fallback
  // that keeps this page consistent with the other list pages); a filtered-empty view stays plain.
  const hasActiveFilters =
    !!params.search ||
    !!params.category ||
    !!params.date_from ||
    !!params.date_to ||
    scope !== 'all';
  const firstRun = isFirstRunEmptyState(data.items.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <DismissableCurrencyHint show={!!currency} />
      {/*
       * A row the API could not convert renders its ORIGINAL figure, which reads exactly like a
       * converted one — so without this the page silently mixes two scales. The API has computed
       * these codes since Phase 3 and nothing had ever read them.
       */}
      <WarningHint show={data.skippedCurrencies.length > 0} parentGap={16}>
        {t('skippedCurrencies', { currencies: fmt.list(data.skippedCurrencies) })}
      </WarningHint>
      <IncomeToolbar
        showScope={groups.length > 0}
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
