'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { InvestmentFormDialog } from '@/app/(protected)/investments/_components/investment-form-dialog';
import { CategorySelect } from '@/components/category-select';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { GroupMultiSelect } from '@/components/group-multi-select';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/investments';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

export function InvestmentsToolbar({
  groups,
  preferredCurrencies,
  supportedCurrencies,
}: {
  groups: InvestmentGroup[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
}) {
  const t = useTranslations('investments');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.investments, { resetPage: true });
  const [createOpen, setCreateOpen] = useState(false);

  const selectedGroupIds = searchParams.getAll('group_ids').map(Number).filter(Boolean);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;

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
    <EntityListToolbar
      route={ROUTES.investments}
      resetPage
      searchAriaLabel="Search investments"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.addInvestment')}
      onAdd={() => setCreateOpen(true)}
      filters={
        <>
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
        </>
      }
      trailing={
        <Button variant="outline" asChild className="min-w-fit flex-1">
          <Link href={ROUTES.data}>
            <Upload className="size-4" />
            {t('toolbar.import')}
          </Link>
        </Button>
      }
    >
      <InvestmentFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        groups={groups}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
