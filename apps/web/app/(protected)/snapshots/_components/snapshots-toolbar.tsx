'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button, SearchInput } from '@repo/ui/components';
import { refreshPrices } from '@/app/(protected)/snapshots/snapshots-actions';
import { CategorySelect } from '@/components/category-select';
import { GroupMultiSelect } from '@/components/group-multi-select';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/investments';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

export function SnapshotsToolbar({ groups }: { groups: InvestmentGroup[] }) {
  const t = useTranslations('snapshots');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.snapshots);
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [refreshing, setRefreshing] = useState(false);

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

  const selectedGroupIds = searchParams.getAll('group_ids').map(Number).filter(Boolean);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;

  useEffect(() => {
    const timer = setTimeout(() => navigate({ search }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function handleGroupToggle(groupId: number) {
    const next = selectedGroupIds.includes(groupId)
      ? selectedGroupIds.filter((id) => id !== groupId)
      : [...selectedGroupIds, groupId];
    navigate({ group_ids: next.map(String) });
  }

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  return (
    <LayoutGroup>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className="min-w-0 flex-1">
          <SearchInput
            aria-label="Search investments"
            placeholder={t('toolbar.searchPlaceholder')}
            value={search}
            surface
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
          />
        </motion.div>

        <motion.div
          layout
          transition={{ duration: ANIMATION_DEFAULT }}
          className="flex flex-wrap items-center gap-x-3 gap-y-2 basis-full lg:basis-auto"
        >
          {groups.length > 0 && (
            <GroupMultiSelect
              groups={groups}
              selectedIds={selectedGroupIds}
              onToggle={handleGroupToggle}
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
        </motion.div>

        <motion.div
          layout
          transition={{ duration: ANIMATION_DEFAULT }}
          className="basis-full lg:basis-auto"
        >
          <Button
            variant="outline"
            disabled={refreshing}
            onClick={handleRefresh}
            className="w-full lg:w-auto gap-x-1.5"
          >
            <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? t('toolbar.refreshing') : t('toolbar.refresh')}
          </Button>
        </motion.div>
      </div>
    </LayoutGroup>
  );
}
