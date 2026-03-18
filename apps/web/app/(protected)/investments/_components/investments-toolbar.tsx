'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Archive, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Pill,
  SearchInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@repo/ui/components';
import { InvestmentFormDialog } from '@/app/(protected)/investments/_components/investment-form-dialog';
import { INVESTMENT_CATEGORIES } from '@/app/(protected)/investments/investments-form-schema';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/investments';

const DEBOUNCE_MS = 300;
const CATEGORY_ALL = '__all__';

export function InvestmentsToolbar({ groups }: { groups: InvestmentGroup[] }) {
  const t = useTranslations('investments');
  const router = useRouter();
  const searchParams = useSearchParams();
  // Ref keeps searchParams current inside the debounced navigate callback without adding it to the effect dependency array.
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const [, startTransition] = useTransition();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState(searchParams.get('search') ?? '');

  const selectedGroupIds = searchParams.getAll('group_ids').map(Number).filter(Boolean);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;
  const showArchived = searchParams.get('show_archived') === 'true';

  function navigate(overrides: Record<string, string | string[] | null>) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    params.delete('page');
    for (const [key, val] of Object.entries(overrides)) {
      if (val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
        params.delete(key);
      } else if (Array.isArray(val)) {
        params.delete(key);
        val.forEach((v) => params.append(key, v));
      } else {
        params.set(key, val);
      }
    }
    startTransition(() => router.push(`${ROUTES.investments}?${params.toString()}`));
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

      <div className="flex flex-col gap-y-2 toolbar-actions:flex-row toolbar-actions:items-center toolbar-actions:gap-x-3">
        <Select value={selectedCategory} onValueChange={handleCategoryChange}>
          <SelectTrigger className="w-full toolbar-actions:w-auto" surface>
            <span className="truncate">
              {selectedCategory === CATEGORY_ALL
                ? t('toolbar.allCategories')
                : t(`categories.${selectedCategory}`)}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={CATEGORY_ALL}>{t('toolbar.allCategories')}</SelectItem>
            {INVESTMENT_CATEGORIES.map((cat) => (
              <SelectItem key={cat} value={cat}>
                {t(`categories.${cat}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Pill
          active={showArchived}
          aria-pressed={showArchived}
          onClick={() => navigate({ show_archived: showArchived ? null : 'true' })}
          className="w-full toolbar-actions:w-auto"
        >
          <Archive className="size-4" />
          {t('toolbar.showArchived')}
        </Pill>

        <Button blue onClick={() => setCreateOpen(true)} className="w-full toolbar-actions:w-auto">
          <Plus className="size-4" />
          {t('toolbar.addInvestment')}
        </Button>
      </div>

      <InvestmentFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        groups={groups}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
