'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { InvestmentFormDialog } from '@/app/(protected)/investments/_components/investment-form-dialog';
import { CategorySelect } from '@/components/category-select';
import { CollectionMultiSelect } from '@/components/collection-multi-select';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import type { InvestmentCollection } from '@/lib/api/collections';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

export function InvestmentsToolbar({
  collections,
  preferredCurrencies,
  supportedCurrencies,
}: {
  collections: InvestmentCollection[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
}) {
  const t = useTranslations('investments');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.investments, { resetPage: true });
  const [createOpen, setCreateOpen] = useState(false);

  const selectedCollectionIds = searchParams.getAll('collection_ids').map(Number).filter(Boolean);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;

  function handleCollectionToggle(collectionId: number) {
    const next = selectedCollectionIds.includes(collectionId)
      ? selectedCollectionIds.filter((id) => id !== collectionId)
      : [...selectedCollectionIds, collectionId];
    navigate({ collection_ids: next.map(String) });
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
        collections={collections}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
