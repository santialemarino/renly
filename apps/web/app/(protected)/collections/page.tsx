import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { CollectionsDataTable } from '@/app/(protected)/collections/_components/collections-data-table';
import { CollectionsToolbar } from '@/app/(protected)/collections/_components/collections-toolbar';
import { getCollections } from '@/lib/api/collections';
import { getInvestments } from '@/lib/api/investments';
import { getSettings } from '@/lib/api/settings';
import { API_MAX_PAGE_SIZE } from '@/lib/constants/api-constants';
import { ENV_COLLECTION_WARNING_PCT, ENV_MAX_COLLECTIONS } from '@/lib/constants/collections';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('collections');
}

interface CollectionsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
  }>;
}

export default async function CollectionsPage({ searchParams }: CollectionsPageProps) {
  const t = await getTranslations('collections');
  const params = await searchParams;

  const [collections, allCollections, investmentsList, settings] = await Promise.all([
    getCollections({
      search: params.search,
      sortBy: params.sort_by as 'name' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getCollections(),
    getInvestments({ activeOnly: true, pageSize: API_MAX_PAGE_SIZE }),
    getSettings().catch(() => null),
  ]);

  const investments = investmentsList.items.map((inv) => ({ id: inv.id, name: inv.name }));
  const maxCollections = settings?.maxCollections ?? ENV_MAX_COLLECTIONS;
  const collectionWarningPct = settings?.collectionWarningPct ?? ENV_COLLECTION_WARNING_PCT;

  // Teach the empty state only during first-run and only when the user has no collections at all (the
  // unfiltered count) — a returning user or a filtered-empty search gets the plain message.
  const firstRun = isFirstRunEmptyState(allCollections.length === 0, false, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <CollectionsToolbar
        investments={investments}
        collectionCount={allCollections.length}
        maxCollections={maxCollections}
        collectionWarningPct={collectionWarningPct}
      />
      <CollectionsDataTable
        collections={collections}
        investments={investments}
        sortBy={params.sort_by}
        sortOrder={params.sort_order as 'asc' | 'desc' | undefined}
        firstRun={firstRun}
      />
    </div>
  );
}
