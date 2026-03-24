'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { SearchInput } from '@repo/ui/components';
import { CategorySelect } from '@/components/category-select';
import { GroupMultiSelect } from '@/components/group-multi-select';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/investments';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';

export function SnapshotsToolbar({ groups }: { groups: InvestmentGroup[] }) {
  const t = useTranslations('snapshots');
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const [, startTransition] = useTransition();
  const [search, setSearch] = useState(searchParams.get('search') ?? '');

  const selectedGroupIds = searchParams.getAll('group_ids').map(Number).filter(Boolean);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;

  function navigate(overrides: Record<string, string | string[] | null>) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
        params.delete(key);
      } else if (Array.isArray(val)) {
        params.delete(key);
        val.forEach((v) => params.append(key, v));
      } else {
        params.set(key, val);
      }
    });
    startTransition(() => router.push(`${ROUTES.snapshots}?${params.toString()}`));
  }

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
            aria-label={t('toolbar.searchPlaceholder')}
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
      </div>
    </LayoutGroup>
  );
}
