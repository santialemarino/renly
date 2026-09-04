'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { PRIVATE_SCOPE } from '@/app/(protected)/_components/entry-scope-field';
import { ExpenseFormDialog } from '@/app/(protected)/_components/expense-form-dialog';
import {
  LinkedPlanAmountMismatchDialog,
  type LinkedPlanMismatch,
} from '@/app/(protected)/_components/linked-plan-amount-mismatch-dialog';
import { SharedExpenseFormDialog } from '@/app/(protected)/_components/shared-expense-form-dialog';
import { ExpenseCategorySelect } from '@/app/(protected)/expenses/_components/expense-category-select';
import { PaymentMethodSelect } from '@/app/(protected)/expenses/_components/payment-method-select';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ScopePill } from '@/components/scope-pill';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Group } from '@/lib/api/groups';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { Subscription } from '@/lib/api/subscriptions';
import type { ListScope } from '@/lib/api/types';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import type { ExpenseHandover } from '@/lib/entry-handover';
import { useDeferredDialogSwap } from '@/lib/hooks/use-deferred-dialog-swap';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { resolveListScope } from '@/lib/list-scope';

export function ExpensesToolbar({
  showScope,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  accounts,
  groups,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
  timeZone,
}: {
  // Whether the caller belongs to any group at all — the one signal that turns the scope filter on,
  // so a solo user (every public user at launch) sees no added control.
  showScope?: boolean;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  accounts?: Account[];
  // The groups the user belongs to. Empty for every solo user, which turns the scope control off
  // entirely — X3's rule, and the state every public user starts in.
  groups?: Group[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  /*
   * The user's stored timezone, for the shared form's default date.
   *
   * Every other dated form in the app threads it and this one did not, so a shared expense started
   * from here defaulted to the BROWSER's today while the same form opened from the group hub — or the
   * income form beside it — used the user's. Two doors into one form disagreeing by a day, for anyone
   * whose stored zone is not the machine's.
   */
  timeZone?: string;
}) {
  const t = useTranslations('expenses');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.expenses, { resetPage: true });
  // Amount-mismatch follow-up prompt (Phase 3, follow-up Item 6). The expense form
  // fires onLinkedPlanSave only when the saved amount differs from the linked plan's
  // current amount — we stash it here so the dialog survives the form's close animation.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);
  /*
   * Which form the Add button is currently showing — the private one, or a group's shared-expense one
   * — and what it opens on. Held here rather than inside either dialog because the swap replaces the
   * whole form: a private expense and a shared one are separate records in separate tables.
   */
  const {
    open: createOpen,
    setOpen: setCreateOpen,
    target: draft,
    start,
    swapTo,
  } = useDeferredDialogSwap<{ scope: string; prefill?: ExpenseHandover }>({ scope: PRIVATE_SCOPE });

  // The FILTER's scope, distinct from the form scope above, which says which RECORD is being
  // written. Same word, two different questions, so they are named apart.
  const scopeFilter = resolveListScope(searchParams.get('scope') ?? undefined);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;
  const selectedPaymentMethod = searchParams.get('payment_method') ?? CATEGORY_ALL;
  const activeGroups = groups ?? [];
  const scopedGroup = activeGroups.find((group) => String(group.id) === draft.scope);

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  function handlePaymentMethodChange(method: string) {
    navigate({ payment_method: method === CATEGORY_ALL ? null : method });
  }

  // The Add button always starts a NEW entry, so it opens the private form carrying nothing: values
  // left over from a previous swap must not seed it.
  function handleAdd() {
    start({ scope: PRIVATE_SCOPE });
  }

  /*
   * The FILTER's scope, which is a different thing from the form swap above — that one hands an
   * in-progress entry between the private and the shared FORM. Named apart on purpose: one decides
   * which rows are read, the other which record is being written, and collapsing them would be the
   * mode X2 exists to prevent.
   *
   * 'all' clears the param rather than writing it, so the default view has a clean URL and a shared
   * link cannot pin somebody into a narrower list than they meant to send.
   */
  function handleScopeFilterChange(next: ListScope) {
    navigate({ scope: next === 'all' ? null : next });
  }

  return (
    <EntityListToolbar
      route={ROUTES.expenses}
      resetPage
      searchAriaLabel="Search expenses"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      addLabel={t('toolbar.addExpense')}
      onAdd={handleAdd}
      filters={
        <>
          {showScope && <ScopePill value={scopeFilter} onChange={handleScopeFilterChange} />}
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
        accounts={accounts}
        open={createOpen && draft.scope === PRIVATE_SCOPE}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={activeObligations}
        activeSubscriptions={activeSubscriptions}
        activeInstallments={activeInstallments}
        scopeGroups={activeGroups}
        onScopeChange={(scope, values) => swapTo({ scope, prefill: values })}
        prefill={draft.prefill}
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

      {/*
       * Mounted only once a group is actually chosen. The dialog reads that group's shared accounts
       * when it opens, so rendering one per group up front would be a request each for a form the
       * user has not asked for.
       */}
      {scopedGroup && (
        <SharedExpenseFormDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          group={scopedGroup}
          prefill={draft.prefill}
          accounts={accounts}
          creditCards={creditCards}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          timeZone={timeZone}
          scopeGroups={activeGroups}
          onScopeChange={(scope, values) => swapTo({ scope, prefill: values })}
          onSuccess={() => router.refresh()}
        />
      )}

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
