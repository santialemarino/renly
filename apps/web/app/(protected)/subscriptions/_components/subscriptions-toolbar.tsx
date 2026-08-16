'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { SubscriptionFormDialog } from '@/app/(protected)/subscriptions/_components/subscription-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';

interface SubscriptionsToolbarProps {
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  // Accounts the optional default funding account can be picked from.
  accounts?: Account[];
}

export function SubscriptionsToolbar({
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  accounts,
}: SubscriptionsToolbarProps) {
  const t = useTranslations('subscriptions');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <EntityListToolbar
      route={ROUTES.subscriptions}
      searchAriaLabel="Search subscriptions"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.add')}
      onAdd={() => setCreateOpen(true)}
    >
      <SubscriptionFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        accounts={accounts}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
