import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { SnapshotsGrid } from '@/app/(protected)/snapshots/_components/snapshots-grid';
import { SnapshotsToolbar } from '@/app/(protected)/snapshots/_components/snapshots-toolbar';
import { ConceptHint } from '@/components/concept-hint';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { HELP_ANCHORS } from '@/config/routes';
import { getGroups } from '@/lib/api/investments';
import { getSettings } from '@/lib/api/settings';
import { getSnapshotGrid } from '@/lib/api/snapshots';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('snapshots');
}

interface SnapshotsPageProps {
  searchParams: Promise<{
    search?: string;
    group_ids?: string | string[];
    category?: string;
    sort_by?: string;
    sort_order?: string;
  }>;
}

export default async function SnapshotsPage({ searchParams }: SnapshotsPageProps) {
  const t = await getTranslations('snapshots');
  const params = await searchParams;
  const cookieStore = await cookies();

  const groupIdsRaw = params.group_ids;
  const groupIds = groupIdsRaw
    ? (Array.isArray(groupIdsRaw) ? groupIdsRaw : [groupIdsRaw]).map(Number).filter(Boolean)
    : undefined;

  const settings = await getSettings().catch(() => null);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const secondary = settings?.secondaryCurrency ?? null;
  const displayCurrencies = secondary
    ? [primary, secondary, ORIGINAL_CURRENCY]
    : [primary, ORIGINAL_CURRENCY];

  // Validate saved cookie against current settings — fall back to primary if stale.
  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const activeCurrency =
    savedCurrency && displayCurrencies.includes(savedCurrency) ? savedCurrency : primary;
  const currency = activeCurrency !== ORIGINAL_CURRENCY ? activeCurrency : undefined;

  const [grid, groups] = await Promise.all([
    getSnapshotGrid({
      search: params.search,
      groupIds,
      category: params.category,
      currency,
      sortBy: params.sort_by,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getGroups(),
  ]);

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || !!groupIds || !!params.category;
  const firstRun = isFirstRunEmptyState(grid.rows.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <DismissableCurrencyHint show={!!currency} />
      <SnapshotsToolbar groups={groups} />
      {/* Concept nudge (shown once there are investments to snapshot; the empty state teaches the rest). */}
      <ConceptHint
        storageKey="snapshots-intro-dismissed"
        anchor={HELP_ANCHORS.snapshots}
        show={grid.rows.length > 0}
      >
        {t('intro')}
      </ConceptHint>
      <SnapshotsGrid grid={grid} firstRun={firstRun} />
    </div>
  );
}
