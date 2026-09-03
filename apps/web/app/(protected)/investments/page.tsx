import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { InvestmentsDataTable } from '@/app/(protected)/investments/_components/investments-data-table';
import { InvestmentsToolbar } from '@/app/(protected)/investments/_components/investments-toolbar';
import { SampleInvestmentsTable } from '@/app/(protected)/investments/_components/sample-investments-table';
import { getCollections } from '@/lib/api/collections';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getGroups } from '@/lib/api/groups';
import { getInvestments } from '@/lib/api/investments';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { resolveListScope } from '@/lib/list-scope';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('investments');
}

interface InvestmentsPageProps {
  searchParams: Promise<{
    search?: string;
    collection_ids?: string | string[];
    category?: string;
    page?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
    scope?: string;
  }>;
}

export default async function InvestmentsPage({ searchParams }: InvestmentsPageProps) {
  const t = await getTranslations('investments');
  const params = await searchParams;

  const collectionIdsRaw = params.collection_ids;
  const collectionIds = collectionIdsRaw
    ? (Array.isArray(collectionIdsRaw) ? collectionIdsRaw : [collectionIdsRaw])
        .map(Number)
        .filter(Boolean)
    : undefined;

  /*
   * The page always asks for `all` — grouped is the default view (X2) — while the endpoint's own
   * default stays `private`, which is what keeps the four other pages that read this list as a picker
   * showing only the caller's own holdings.
   */
  const scope = resolveListScope(params.scope);

  const [data, collections, settings, supportedCurrencies, groups] = await Promise.all([
    getInvestments({
      scope,
      search: params.search,
      collectionIds,
      category: params.category,
      activeOnly: params.show_archived !== 'true',
      page: params.page ? Number(params.page) : 1,
      sortBy: params.sort_by as 'name' | 'category' | 'base_currency' | 'broker' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getCollections(),
    getSettings().catch(() => null),
    getSupportedCurrencies().catch(() => undefined),
    /*
     * The groups the user belongs to, which is the ONE thing that turns the scope pill on — the same
     * signal the entry forms' scope control already uses (X3). Read separately from `sections` on
     * purpose: `sections` follows the current filter, so a page narrowed to "Yours" would otherwise
     * lose the control that narrowed it. Empty for every solo user, and then nothing renders.
     */
    getGroups().catch(() => []),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  // Show this section's first-run sample only while it's empty; fetch the flag just then so a
  // populated section never pays for the extra read.
  const showSample =
    data.items.length === 0
      ? ((await getOnboardingStatus().catch(() => null))?.sampleInvestments ?? false)
      : false;

  // Once the sample is retired, a still-onboarding user gets the teaching empty state (the fallback
  // that keeps this page consistent with the other list pages); a filtered-empty view stays plain.
  const hasActiveFilters =
    !!params.search ||
    !!collectionIds ||
    !!params.category ||
    params.show_archived === 'true' ||
    scope !== 'all';
  const firstRun = isFirstRunEmptyState(data.items.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <InvestmentsToolbar
        collections={collections}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        showScope={groups.length > 0}
      />
      {showSample ? (
        <SampleInvestmentsTable />
      ) : (
        <InvestmentsDataTable
          data={data}
          collections={collections}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          firstRun={firstRun}
        />
      )}
    </div>
  );
}
