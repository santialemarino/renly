import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { SnapshotsGrid } from '@/app/(protected)/snapshots/_components/snapshots-grid';
import { SnapshotsToolbar } from '@/app/(protected)/snapshots/_components/snapshots-toolbar';
import { ConceptHint } from '@/components/concept-hint';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { WarningHint } from '@/components/styled-hint';
import { HELP_ANCHORS } from '@/config/routes';
import { getCollections } from '@/lib/api/collections';
import { getGroups } from '@/lib/api/groups';
import { getSettings } from '@/lib/api/settings';
import { getSnapshotGrid } from '@/lib/api/snapshots';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { getFormatters } from '@/lib/i18n/formatters-server';
import { resolveGridInterval, resolveListScope } from '@/lib/list-scope';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('snapshots');
}

interface SnapshotsPageProps {
  searchParams: Promise<{
    search?: string;
    collection_ids?: string | string[];
    category?: string;
    sort_by?: string;
    sort_order?: string;
    scope?: string;
    interval?: string;
  }>;
}

export default async function SnapshotsPage({ searchParams }: SnapshotsPageProps) {
  const fmt = await getFormatters();
  const t = await getTranslations('snapshots');
  const params = await searchParams;
  const cookieStore = await cookies();

  const collectionIdsRaw = params.collection_ids;
  const collectionIds = collectionIdsRaw
    ? (Array.isArray(collectionIdsRaw) ? collectionIdsRaw : [collectionIdsRaw])
        .map(Number)
        .filter(Boolean)
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

  const scope = resolveListScope(params.scope);
  // Weekly is a TOGGLE, not derived: this grid mixes private holdings (no cadence at all) with the
  // holdings of several pots that may each declare a different one, so nothing can derive it honestly.
  const interval = resolveGridInterval(params.interval);

  const [grid, collections, groups] = await Promise.all([
    getSnapshotGrid({
      scope,
      interval,
      search: params.search,
      collectionIds,
      category: params.category,
      currency,
      sortBy: params.sort_by,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getCollections(),
    /*
     * The groups the user belongs to, which is the ONE signal that turns the scope filter on — the
     * same one the entry forms' scope control uses (X3). Read separately from `sections` on purpose:
     * `sections` follows the current filter, so a grid narrowed to "Yours" would otherwise lose the
     * control that narrowed it. Empty for every solo user, and then nothing renders.
     */
    getGroups().catch(() => []),
  ]);

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters =
    !!params.search || !!collectionIds || !!params.category || scope !== 'all';
  const firstRun = isFirstRunEmptyState(grid.rows.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <DismissableCurrencyHint show={!!currency} />
      <SnapshotsToolbar collections={collections} showScope={groups.length > 0} />
      {/*
       * An investment whose currency has no stored rate is EXCLUDED from the grid entirely, and the
       * API has reported which ones since Phase 3 — this page had never rendered it, so such a
       * holding simply vanished from a grid claiming to show everything.
       */}
      <WarningHint show={grid.skippedInvestments.length > 0} parentGap={16}>
        {t('grid.skippedInvestments', {
          names: fmt.list(grid.skippedInvestments.map((s) => `${s.name} (${s.baseCurrency})`)),
        })}
      </WarningHint>
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
