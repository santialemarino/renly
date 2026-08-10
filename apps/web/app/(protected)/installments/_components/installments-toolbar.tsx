'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { InstallmentFormDialog } from '@/app/(protected)/installments/_components/installment-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';

interface InstallmentsToolbarProps {
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  // Accounts the optional default funding account can be picked from.
  accounts?: Account[];
}

export function InstallmentsToolbar({
  preferredCurrencies,
  creditCards,
  accounts,
}: InstallmentsToolbarProps) {
  const t = useTranslations('installments');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <EntityListToolbar
      route={ROUTES.installments}
      searchAriaLabel="Search installments"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.add')}
      onAdd={() => setCreateOpen(true)}
    >
      <InstallmentFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        accounts={accounts}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
