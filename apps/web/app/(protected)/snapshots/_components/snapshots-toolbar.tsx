'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import {
  Pill,
  SearchInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@repo/ui/components';
import { INVESTMENT_CATEGORIES } from '@/app/(protected)/investments/investments-form-schema';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/investments';

const DEBOUNCE_MS = 300;
const CATEGORY_ALL = '__all__';

export function SnapshotsToolbar({ groups }: { groups: InvestmentGroup[] }) {
  const t = useTranslations('snapshots');
  const tCommon = useTranslations('common');
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
    <div className="@container flex flex-col gap-y-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3">
      <SearchInput
        aria-label={t('toolbar.searchPlaceholder')}
        placeholder={t('toolbar.searchPlaceholder')}
        value={search}
        surface
        onChange={(e) => setSearch(e.target.value)}
        onClear={() => setSearch('')}
        containerClassName="w-full sm:flex-1"
      />

      {groups.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5">
          {groups.map((group) => (
            <Pill
              key={group.id}
              active={selectedGroupIds.includes(group.id)}
              aria-pressed={selectedGroupIds.includes(group.id)}
              onClick={() => handleGroupToggle(group.id)}
            >
              {group.name}
            </Pill>
          ))}
        </div>
      )}

      <Select value={selectedCategory} onValueChange={handleCategoryChange}>
        <SelectTrigger className="w-full sm:w-auto" surface>
          <span className="truncate">
            {selectedCategory === CATEGORY_ALL
              ? tCommon('allCategories')
              : tCommon(`categories.${selectedCategory}`)}
          </span>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={CATEGORY_ALL}>{tCommon('allCategories')}</SelectItem>
          {INVESTMENT_CATEGORIES.map((cat) => (
            <SelectItem key={cat} value={cat}>
              {tCommon(`categories.${cat}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
