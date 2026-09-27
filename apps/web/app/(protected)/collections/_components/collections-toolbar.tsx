'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { CollectionFormDialog } from '@/app/(protected)/collections/_components/collection-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { WarningHint } from '@/components/styled-hint';
import { ROUTES } from '@/config/routes';

interface CollectionsToolbarProps {
  investments: { id: number; name: string }[];
  collectionCount: number;
  maxCollections: number;
  collectionWarningPct: number | null;
}

export function CollectionsToolbar({
  investments,
  collectionCount,
  maxCollections,
  collectionWarningPct,
}: CollectionsToolbarProps) {
  const t = useTranslations('collections');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  const nearLimit =
    collectionWarningPct !== null &&
    collectionCount >= maxCollections * (collectionWarningPct / 100);
  const atLimit = collectionCount >= maxCollections;

  return (
    <div className="flex flex-col gap-y-2">
      <EntityListToolbar
        route={ROUTES.collections}
        searchPlaceholder={t('toolbar.searchPlaceholder')}
        addLabel={t('toolbar.addCollection')}
        onAdd={() => setCreateOpen(true)}
        addDisabled={atLimit}
      >
        <CollectionFormDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          investments={investments}
          onSuccess={() => router.refresh()}
        />
      </EntityListToolbar>

      {/* Below the toolbar rather than inside it: the toolbar's row is for controls, and a hint in a
          wrapping flex row would be laid out as one more item beside them. */}
      <WarningHint show={nearLimit && !atLimit} parentGap={8}>
        {t('softLimit.approaching', { count: collectionCount, max: maxCollections })}
      </WarningHint>
      <WarningHint show={atLimit} parentGap={8}>
        {t('softLimit.reached', { max: maxCollections })}
      </WarningHint>
    </div>
  );
}
