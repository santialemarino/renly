'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { PaymentObligationFormDialog } from '@/app/(protected)/payment-obligations/_components/payment-obligation-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';

interface PaymentObligationsToolbarProps {
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
}

export function PaymentObligationsToolbar({
  preferredCurrencies,
  creditCards,
}: PaymentObligationsToolbarProps) {
  const t = useTranslations('paymentObligations');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <EntityListToolbar
      route={ROUTES.paymentObligations}
      searchAriaLabel="Search payment obligations"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      showArchivedLabel={t('toolbar.showArchived')}
      addLabel={t('toolbar.add')}
      onAdd={() => setCreateOpen(true)}
    >
      <PaymentObligationFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        onSuccess={() => router.refresh()}
      />
    </EntityListToolbar>
  );
}
