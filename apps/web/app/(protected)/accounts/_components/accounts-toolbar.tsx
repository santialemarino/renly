'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { AccountFormDialog } from '@/app/(protected)/accounts/_components/account-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';

interface AccountsToolbarProps {
  preferredCurrencies?: string[];
}

export function AccountsToolbar({ preferredCurrencies }: AccountsToolbarProps) {
  const t = useTranslations('accounts');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <EntityListToolbar
      route={ROUTES.accounts}
      searchAriaLabel="Search accounts"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.add')}
      onAdd={() => setCreateOpen(true)}
    >
      <AccountFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
