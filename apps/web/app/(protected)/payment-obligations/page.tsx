import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PaymentObligationsTable } from '@/app/(protected)/payment-obligations/_components/payment-obligations-table';
import { PaymentObligationsToolbar } from '@/app/(protected)/payment-obligations/_components/payment-obligations-toolbar';
import { getAccounts } from '@/lib/api/accounts';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import {
  getPaymentObligations,
  type PaymentObligationSortField,
} from '@/lib/api/payment-obligations';
import { getPageSettings, getSettings } from '@/lib/api/settings';
import type { SortOrder } from '@/lib/api/types';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('paymentObligations');
}

interface PaymentObligationsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function PaymentObligationsPage({
  searchParams,
}: PaymentObligationsPageProps) {
  const t = await getTranslations('paymentObligations');
  const params = await searchParams;
  const cookieStore = await cookies();

  const settingsRead = getSettings().catch(() => null);
  // All at once, bar one: the list waits only for the settings it is priced in (request-memoized,
  // shared with the layout on a full load); the pickers' reads start at once.
  const [{ settings, creditCards }, supportedCurrencies, accounts, obligations] = await Promise.all(
    [
      getPageSettings(),
      // The obligation form and the Mark-Paid expense dialog restrict their currency picker to the
      // convertible set; on a fetch error the picker degrades to the full list and the API's 422 still
      // guards.
      getSupportedCurrencies().catch(() => undefined),
      /*
       * Accounts for the optional "paid from" link on a non-card Mark-Paid expense and for an
       * obligation's default funding account (empty on error → the fields hide themselves). Archived
       * ones are included so a stored link or default that has since been archived still renders by
       * name instead of a blank picker; the pickers only ever OFFER active accounts.
       */
      getAccounts({ showArchived: true }).catch(() => []),
      settingsRead.then((pageSettings) =>
        getPaymentObligations({
          search: params.search,
          sortBy: params.sort_by as PaymentObligationSortField | undefined,
          sortOrder: params.sort_order as SortOrder | undefined,
          showArchived: params.show_archived === 'true',
          currency: resolveActiveCurrency(cookieStore, pageSettings),
        }),
      ),
    ],
  );
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;
  const currency = resolveActiveCurrency(cookieStore, settings);

  const hasActiveFilters = !!params.search || params.show_archived === 'true';
  const firstRun = isFirstRunEmptyState(obligations.length === 0, hasActiveFilters, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <PaymentObligationsToolbar
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        accounts={accounts}
      />
      <PaymentObligationsTable
        obligations={obligations}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        accounts={accounts}
        activeCurrency={currency}
        firstRun={firstRun}
      />
    </div>
  );
}
