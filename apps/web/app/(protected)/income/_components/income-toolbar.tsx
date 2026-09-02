'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import {
  PRIVATE_SCOPE,
  type IncomeHandover,
} from '@/app/(protected)/_components/entry-scope-field';
import { SharedIncomeFormDialog } from '@/app/(protected)/_components/shared-income-form-dialog';
import { IncomeCategorySelect } from '@/app/(protected)/income/_components/income-category-select';
import { IncomeFormDialog } from '@/app/(protected)/income/_components/income-form-dialog';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import { DIALOG_EXIT_MS } from '@/lib/constants/animations';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

export function IncomeToolbar({
  preferredCurrencies,
  supportedCurrencies,
  accounts,
  groups,
  timeZone,
}: {
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  accounts?: Account[];
  // The groups the user belongs to, which is what turns the entry form's scope control on. Empty for
  // a solo user, and the control then renders nothing at all.
  groups?: Group[];
  timeZone?: string;
}) {
  const t = useTranslations('income');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.income, { resetPage: true });
  const [createOpen, setCreateOpen] = useState(false);
  /*
   * Which form the Add button is currently showing: the private one, or a group's shared-income one.
   * Held here rather than inside either dialog because the swap replaces the whole form — a private
   * income entry and a shared one are separate records in separate tables.
   */
  const [scope, setScope] = useState<string>(PRIVATE_SCOPE);
  const [handover, setHandover] = useState<IncomeHandover | undefined>(undefined);
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
  const activeGroups = groups ?? [];
  const scopedGroup = activeGroups.find((group) => String(group.id) === scope);

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
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
  function handleScopeChange(next: string, values: IncomeHandover) {
    setHandover(values);
    setCreateOpen(false);
    swapTimer.current = setTimeout(() => {
      swapTimer.current = null;
      setScope(next);
      setCreateOpen(true);
    }, DIALOG_EXIT_MS);
  }

  return (
    <EntityListToolbar
      route={ROUTES.income}
      resetPage
      searchAriaLabel="Search income"
      searchPlaceholder={t('toolbar.searchPlaceholder')}
      addLabel={t('toolbar.addIncome')}
      onAdd={handleAdd}
      filters={
        <IncomeCategorySelect
          value={selectedCategory}
          onValueChange={handleCategoryChange}
          surface
          className="min-w-fit flex-1"
        />
      }
    >
      <IncomeFormDialog
        open={createOpen && scope === PRIVATE_SCOPE}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={accounts}
        scopeGroups={activeGroups}
        onScopeChange={handleScopeChange}
        prefill={handover}
        onSuccess={() => router.refresh()}
      />

      {/*
       * Mounted only once a group is actually chosen. The dialog reads that group's shared accounts,
       * assets and income history when it opens, so rendering one per group up front would be three
       * requests each for a form the user has not asked for.
       */}
      {scopedGroup && (
        <SharedIncomeFormDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          group={scopedGroup}
          prefill={handover}
          accounts={accounts}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          timeZone={timeZone}
          scopeGroups={activeGroups}
          onScopeChange={handleScopeChange}
          onSuccess={() => router.refresh()}
        />
      )}
    </EntityListToolbar>
  );
}
