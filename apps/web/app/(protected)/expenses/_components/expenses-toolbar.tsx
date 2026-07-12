'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { ExpenseFormDialog } from '@/app/(protected)/_components/expense-form-dialog';
import {
  LinkedPlanAmountMismatchDialog,
  type LinkedPlanMismatch,
} from '@/app/(protected)/_components/linked-plan-amount-mismatch-dialog';
import { ExpenseCategorySelect } from '@/app/(protected)/expenses/_components/expense-category-select';
import { PaymentMethodSelect } from '@/app/(protected)/expenses/_components/payment-method-select';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { Subscription } from '@/lib/api/subscriptions';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

export function ExpensesToolbar({
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
}: {
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
}) {
  const t = useTranslations('expenses');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.expenses, { resetPage: true });
  const [createOpen, setCreateOpen] = useState(false);
  // Amount-mismatch follow-up prompt (Phase 3, follow-up Item 6). The expense form
  // fires onLinkedPlanSave only when the saved amount differs from the linked plan's
  // current amount — we stash it here so the dialog survives the form's close animation.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);

  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;
  const selectedPaymentMethod = searchParams.get('payment_method') ?? CATEGORY_ALL;

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  function handlePaymentMethodChange(method: string) {
    navigate({ payment_method: method === CATEGORY_ALL ? null : method });
  }

  return (
    <EntityListToolbar
      route={ROUTES.expenses}
      resetPage
      searchAriaLabel="Search expenses"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      addLabel={t('toolbar.addExpense')}
      onAdd={() => setCreateOpen(true)}
      filters={
        <>
          <ExpenseCategorySelect
            value={selectedCategory}
            onValueChange={handleCategoryChange}
            surface
            className="min-w-fit flex-1"
          />
          <PaymentMethodSelect
            value={selectedPaymentMethod}
            onValueChange={handlePaymentMethodChange}
            surface
            className="min-w-fit flex-1"
          />
        </>
      }
    >
      <ExpenseFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={activeObligations}
        activeSubscriptions={activeSubscriptions}
        activeInstallments={activeInstallments}
        onSuccess={() => router.refresh()}
        onLinkedPlanSave={(values, plan) =>
          setMismatch({
            type: plan.type,
            planId: plan.id,
            planName: plan.name,
            enteredAmount: values.amount,
            currentAmount: plan.amount,
            currency: plan.currency,
          })
        }
      />

      <LinkedPlanAmountMismatchDialog
        mismatch={mismatch}
        onClose={() => setMismatch(null)}
        onConfirmed={() => {
          setMismatch(null);
          router.refresh();
        }}
      />
    </EntityListToolbar>
  );
}
