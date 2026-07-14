'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { CreditCardFormDialog } from '@/app/(protected)/_components/credit-card-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';

export function CreditCardsToolbar({ preferredCurrencies }: { preferredCurrencies?: string[] }) {
  const t = useTranslations('creditCards');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <EntityListToolbar
      route={ROUTES.creditCards}
      searchAriaLabel="Search credit cards"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.addCard')}
      onAdd={() => setCreateOpen(true)}
    >
      <CreditCardFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
