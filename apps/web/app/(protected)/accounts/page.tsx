import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { AccountsTable } from '@/app/(protected)/accounts/_components/accounts-table';
import { AccountsToolbar } from '@/app/(protected)/accounts/_components/accounts-toolbar';
import { ConceptHint } from '@/components/concept-hint';
import { HELP_ANCHORS } from '@/config/routes';
import { getAccounts, type AccountSortField } from '@/lib/api/accounts';
import { getPageSettings } from '@/lib/api/settings';
import type { SortOrder } from '@/lib/api/types';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('accounts');
}

interface AccountsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function AccountsPage({ searchParams }: AccountsPageProps) {
  const t = await getTranslations('accounts');
  const params = await searchParams;

  const { settings } = await getPageSettings();
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const accounts = await getAccounts({
    search: params.search,
    sortBy: params.sort_by as AccountSortField | undefined,
    sortOrder: params.sort_order as SortOrder | undefined,
    showArchived: params.show_archived === 'true',
  });
  /*
   * The transfer dialog's pickers need EVERY account, not the page's filtered view — searching
   * "Galicia" must not make the destination list empty and the transfer uncreatable. Every other page
   * that renders an account picker fetches unfiltered for the same reason (those pass
   * `showArchived: true`, since their pickers must be able to NAME an already-stored archived link;
   * the transfer pickers deliberately exclude archived accounts, so this call stays active-only).
   */
  const allAccounts = await getAccounts();

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun = isFirstRunEmptyState(accounts.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      {/*
       * Sets the honest expectation for a derived balance without nudging toward completeness:
       * it points at reconciliation (the intended mechanism), never at "you should link more".
       * Shown only once there is an account to reconcile.
       */}
      <ConceptHint
        storageKey="accounts-reconcile-hint-dismissed"
        anchor={HELP_ANCHORS.accuracy}
        show={accounts.length > 0}
      >
        {t('reconcileHint')}
      </ConceptHint>
      <AccountsToolbar preferredCurrencies={preferredCurrencies} />
      <AccountsTable
        accounts={accounts}
        allAccounts={allAccounts}
        preferredCurrencies={preferredCurrencies}
        firstRun={firstRun}
        timeZone={settings?.timezone ?? undefined}
      />
    </div>
  );
}
