'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { IncomeCategorySelect } from '@/app/(protected)/income/_components/income-category-select';
import { IncomeFormDialog } from '@/app/(protected)/income/_components/income-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

export function IncomeToolbar({
  preferredCurrencies,
  supportedCurrencies,
}: {
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
}) {
  const t = useTranslations('income');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.income, { resetPage: true });
  const [createOpen, setCreateOpen] = useState(false);

  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  return (
    <EntityListToolbar
      route={ROUTES.income}
      resetPage
      searchAriaLabel="Search income"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      addLabel={t('toolbar.addIncome')}
      onAdd={() => setCreateOpen(true)}
      filters={
        <IncomeCategorySelect
          value={selectedCategory}
          onValueChange={handleCategoryChange}
          surface
          className="min-w-fit flex-1"
        />
      }
    >
      <IncomeFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
