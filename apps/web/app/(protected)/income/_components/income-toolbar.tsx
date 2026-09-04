'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { PRIVATE_SCOPE } from '@/app/(protected)/_components/entry-scope-field';
import { IncomeFormDialog } from '@/app/(protected)/_components/income-form-dialog';
import { SharedIncomeFormDialog } from '@/app/(protected)/_components/shared-income-form-dialog';
import { IncomeCategorySelect } from '@/app/(protected)/income/_components/income-category-select';
import { EntityListToolbar } from '@/components/entity-list-toolbar';
import { ScopePill } from '@/components/scope-pill';
import { ROUTES } from '@/config/routes';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import type { ListScope } from '@/lib/api/types';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import type { IncomeHandover } from '@/lib/entry-handover';
import { useDeferredDialogSwap } from '@/lib/hooks/use-deferred-dialog-swap';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { resolveListScope } from '@/lib/list-scope';

export function IncomeToolbar({
  showScope,
  preferredCurrencies,
  supportedCurrencies,
  accounts,
  groups,
  timeZone,
}: {
  // Whether the caller belongs to any group at all — the one signal that turns the scope filter on,
  // so a solo user (every public user at launch) sees no added control.
  showScope?: boolean;
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
  /*
   * Which form the Add button is currently showing — the private one, or a group's shared-income one
   * — and what it opens on. Held here rather than inside either dialog because the swap replaces the
   * whole form: a private income entry and a shared one are separate records in separate tables.
   */
  const {
    open: createOpen,
    setOpen: setCreateOpen,
    target: draft,
    start,
    swapTo,
  } = useDeferredDialogSwap<{ scope: string; prefill?: IncomeHandover }>({ scope: PRIVATE_SCOPE });

  // The FILTER's scope, distinct from the form scope above, which says which RECORD is being
  // written. Same word, two different questions, so they are named apart.
  const scopeFilter = resolveListScope(searchParams.get('scope') ?? undefined);
  const selectedCategory = searchParams.get('category') ?? CATEGORY_ALL;
  const activeGroups = groups ?? [];
  const scopedGroup = activeGroups.find((group) => String(group.id) === draft.scope);

  function handleCategoryChange(cat: string) {
    navigate({ category: cat === CATEGORY_ALL ? null : cat });
  }

  // The Add button always starts a NEW entry, so it opens the private form carrying nothing: values
  // left over from a previous swap must not seed it.
  function handleAdd() {
    start({ scope: PRIVATE_SCOPE });
  }

  /*
   * The FILTER's scope, which is a different thing from the form swap above — that one hands an
   * in-progress entry between the private and the shared FORM. Named apart on purpose: one decides
   * which rows are read, the other which record is being written.
   *
   * 'all' clears the param rather than writing it, so the default view has a clean URL and a shared
   * link cannot pin somebody into a narrower list than they meant to send.
   */
  function handleScopeFilterChange(next: ListScope) {
    navigate({ scope: next === 'all' ? null : next });
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
        <>
          {showScope && <ScopePill value={scopeFilter} onChange={handleScopeFilterChange} />}
          <IncomeCategorySelect
            value={selectedCategory}
            onValueChange={handleCategoryChange}
            surface
            className="min-w-fit flex-1"
          />
        </>
      }
    >
      <IncomeFormDialog
        open={createOpen && draft.scope === PRIVATE_SCOPE}
        onOpenChange={setCreateOpen}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={accounts}
        scopeGroups={activeGroups}
        onScopeChange={(scope, values) => swapTo({ scope, prefill: values })}
        prefill={draft.prefill}
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
          prefill={draft.prefill}
          accounts={accounts}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          timeZone={timeZone}
          scopeGroups={activeGroups}
          onScopeChange={(scope, values) => swapTo({ scope, prefill: values })}
          onSuccess={() => router.refresh()}
        />
      )}
    </EntityListToolbar>
  );
}
