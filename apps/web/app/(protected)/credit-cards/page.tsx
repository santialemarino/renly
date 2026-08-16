import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { CreditCardsTable } from '@/app/(protected)/credit-cards/_components/credit-cards-table';
import { CreditCardsToolbar } from '@/app/(protected)/credit-cards/_components/credit-cards-toolbar';
import { getAccounts } from '@/lib/api/accounts';
import { getCreditCards } from '@/lib/api/credit-cards';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getSettings } from '@/lib/api/settings';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('creditCards');
}

interface CreditCardsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function CreditCardsPage({ searchParams }: CreditCardsPageProps) {
  const t = await getTranslations('creditCards');
  const params = await searchParams;

  const [cards, settings, accounts, supportedCurrencies] = await Promise.all([
    getCreditCards({
      search: params.search,
      sortBy: params.sort_by as 'name' | 'closing_day' | 'due_day' | 'currency' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
      showArchived: params.show_archived === 'true',
    }),
    getSettings().catch(() => null),
    /*
     * Accounts for the optional "paid from" link on a settlement and for a card's default funding
     * account (empty on error → the fields hide themselves). Archived ones are included so a stored
     * default that has since been archived still renders by name instead of a blank picker; the
     * pickers themselves only ever OFFER active accounts.
     */
    getAccounts({ showArchived: true }).catch(() => []),
    // The card form restricts its currency picker to the convertible set, like every other money
    // form; on a fetch error it degrades to the full list and the API's 422 still guards.
    getSupportedCurrencies().catch(() => undefined),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  // Teach the empty state only during first-run (before onboarding is completed) and only when no
  // filter is hiding existing rows — a returning user or a filtered-empty view gets the plain line.
  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun = isFirstRunEmptyState(cards.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <CreditCardsToolbar
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={accounts}
      />
      <CreditCardsTable
        cards={cards}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        accounts={accounts}
        firstRun={firstRun}
      />
    </div>
  );
}
