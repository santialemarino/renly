import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { CreditCardsTable } from '@/app/(protected)/credit-cards/_components/credit-cards-table';
import { CreditCardsToolbar } from '@/app/(protected)/credit-cards/_components/credit-cards-toolbar';
import { getAccounts } from '@/lib/api/accounts';
import { getCreditCards } from '@/lib/api/credit-cards';
import { getLatestRates, getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getSettings } from '@/lib/api/settings';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';
import { rateDateForPair, rateForPair } from '@/lib/utils/settlement-rate';

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

  const [cards, settings, accounts, supportedCurrencies, latestRates] = await Promise.all([
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
    // Only for the estimate beside a cross-currency settlement's implied rate. On error (or before any
    // rate is stored) the estimate is simply omitted — the user's typed amount is still what's recorded,
    // so nothing about the settlement depends on this succeeding.
    getLatestRates().catch(() => null),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;
  /*
   * The OFICIAL pair specifically, never the user's dollar-rate preference: "dólar tarjeta" is built on
   * oficial even for someone viewing MEP, so reading the preference here would be a quiet correctness bug
   * rather than a display choice.
   */
  const oficialRate = rateForPair(latestRates?.rates ?? [], 'USD_ARS_OFICIAL');
  /*
   * The date that rate is FOR, carried so the estimate can name it instead of claiming "today". The
   * settlement being recorded is usually backdated (last month's statement), and the scheduler can be
   * behind, so an undated benchmark contradicts correct entries — it has to say what it is.
   */
  const oficialRateDate = rateDateForPair(latestRates?.rates ?? [], 'USD_ARS_OFICIAL');

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
        oficialRate={oficialRate}
        oficialRateDate={oficialRateDate}
        firstRun={firstRun}
      />
    </div>
  );
}
