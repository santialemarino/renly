'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import {
  PRIVATE_SCOPE,
  type ExpenseHandover,
} from '@/app/(protected)/_components/entry-scope-field';
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
import { DIALOG_EXIT_MS } from '@/lib/constants/animations';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
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
}) {
  const t = useTranslations('expenses');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.expenses, { resetPage: true });
  const [createOpen, setCreateOpen] = useState(false);

  // The FILTER's scope, distinct from the form `scope` below, which says which RECORD is being
  // written. Same word, two different questions, so they are named apart.
  const scopeFilter = resolveListScope(searchParams.get('scope') ?? undefined);
  /*
   * Which form the Add button is currently showing: the private one, or a group's shared-expense
   * one. Held here rather than inside either dialog because the swap replaces the whole form —
   * a private expense and a shared one are separate records in separate tables.
   */
  const [scope, setScope] = useState<string>(PRIVATE_SCOPE);
  const [handover, setHandover] = useState<ExpenseHandover | undefined>(undefined);
  // Amount-mismatch follow-up prompt (Phase 3, follow-up Item 6). The expense form
  // fires onLinkedPlanSave only when the saved amount differs from the linked plan's
  // current amount — we stash it here so the dialog survives the form's close animation.
  const [mismatch, setMismatch] = useState<LinkedPlanMismatch | null>(null);
  // The pending half of a scope swap, so an unmount between the close and the reopen cannot leave a
  // timer waking up to open a dialog on a page that has gone.
  const swapTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (swapTimer.current !== null) clearTimeout(swapTimer.current);
    },
    [],
  );

  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;
  const selectedPaymentMethod = searchParams.get('payment_method') ?? CATEGORY_ALL;
  const activeGroups = groups ?? [];
  const scopedGroup = activeGroups.find((group) => String(group.id) === scope);

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  function handlePaymentMethodChange(method: string) {
    navigate({ payment_method: method === CATEGORY_ALL ? null : method });
  }

  // Opens whichever form the scope currently names, always on a clean slate: the Add button starts a
  // new entry, so a handover left over from a previous swap must not seed it.
  function handleAdd() {
    setHandover(undefined);
    setScope(PRIVATE_SCOPE);
    setCreateOpen(true);
  }

  // Closes the form on screen, then opens the other with what was typed. Sequential rather than
  // simultaneous — see DIALOG_EXIT_MS.
  function handleScopeChange(next: string, values: ExpenseHandover) {
    setHandover(values);
    setCreateOpen(false);
    swapTimer.current = setTimeout(() => {
      swapTimer.current = null;
      setScope(next);
      setCreateOpen(true);
    }, DIALOG_EXIT_MS);
  }

  /*
   * The FILTER's scope, which is a different thing from `handleScopeChange` above — that one hands an
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
        open={createOpen && scope === PRIVATE_SCOPE}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={activeObligations}
        activeSubscriptions={activeSubscriptions}
        activeInstallments={activeInstallments}
        scopeGroups={activeGroups}
        onScopeChange={handleScopeChange}
        prefill={handover}
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
          prefill={handover}
          accounts={accounts}
          creditCards={creditCards}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          scopeGroups={activeGroups}
          onScopeChange={handleScopeChange}
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
