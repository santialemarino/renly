'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@repo/ui/components';
import { refreshPrices } from '@/app/(protected)/snapshots/snapshots-actions';
import { CategorySelect } from '@/components/category-select';
import { CollectionMultiSelect } from '@/components/collection-multi-select';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ScopePill } from '@/components/scope-pill';
import { SegmentedPills } from '@/components/segmented-pills';
import { ROUTES } from '@/config/routes';
import type { InvestmentCollection } from '@/lib/api/collections';
import type { SnapshotGridInterval } from '@/lib/api/snapshots';
import type { ListScope } from '@/lib/api/types';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { resolveGridInterval, resolveListScope } from '@/lib/list-scope';

const INTERVALS: readonly SnapshotGridInterval[] = ['monthly', 'weekly'];

export function SnapshotsToolbar({
  collections,
  showScope,
}: {
  collections: InvestmentCollection[];
  // Whether the caller belongs to any group at all — the one signal that turns the scope filter on,
  // so a solo user (every public user at launch) sees no added control.
  showScope?: boolean;
}) {
  const t = useTranslations('snapshots');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.snapshots);
  const [refreshing, setRefreshing] = useState(false);

  const selectedCollectionIds = searchParams.getAll('collection_ids').map(Number).filter(Boolean);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;
  const scope = resolveListScope(searchParams.get('scope') ?? undefined);
  const interval = resolveGridInterval(searchParams.get('interval') ?? undefined);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      const result = await refreshPrices();
      toast.success(t('toolbar.refreshSuccess', { prices: result.pricesStored }));
      router.refresh();
    } catch {
      toast.error(t('toolbar.refreshError'));
    } finally {
      setRefreshing(false);
    }
  }

  function handleCollectionToggle(collectionId: number) {
    const next = selectedCollectionIds.includes(collectionId)
      ? selectedCollectionIds.filter((id) => id !== collectionId)
      : [...selectedCollectionIds, collectionId];
    navigate({ collection_ids: next.map(String) });
  }

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  // Both clear the param on their default value, so the ordinary view has a clean URL.
  function handleScopeChange(next: ListScope) {
    navigate({ scope: next === 'all' ? null : next });
  }

  function handleIntervalChange(next: SnapshotGridInterval) {
    navigate({ interval: next === 'monthly' ? null : next });
  }

  return (
    <EntityListToolbar
      route={ROUTES.snapshots}
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      filters={
        <>
          {showScope && <ScopePill value={scope} onChange={handleScopeChange} />}
          {/*
           * The column grid, as a TOGGLE rather than something derived: this grid mixes private
           * holdings (which declare no cadence) with the holdings of several pots that may each
           * declare a different one, so there is no single honest answer to derive. §9's cadence
           * still shows up per row, as the freshness indicator, which is where it belongs.
           */}
          <SegmentedPills
            value={interval}
            options={INTERVALS}
            onChange={handleIntervalChange}
            label={t('toolbar.interval.label')}
            labelFor={(option) => t(`toolbar.interval.${option}`)}
          />
          {collections.length > 0 && (
            <CollectionMultiSelect
              collections={collections}
              selectedIds={selectedCollectionIds}
              onToggle={handleCollectionToggle}
              surface
              className="min-w-fit flex-1"
            />
          )}
          <CategorySelect
            value={selectedCategory}
            onValueChange={handleCategoryChange}
            surface
            className="min-w-fit flex-1"
          />
        </>
      }
      trailing={
        <Button
          variant="outline"
          disabled={refreshing}
          onClick={handleRefresh}
          className="min-w-fit flex-1 gap-x-1.5"
        >
          <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? t('toolbar.refreshing') : t('toolbar.refresh')}
        </Button>
      }
    />
  );
}
