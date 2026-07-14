import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PaymentsCalendarHeader } from '@/app/(protected)/payments-calendar/_components/payments-calendar-header';
import { PaymentsCalendarList } from '@/app/(protected)/payments-calendar/_components/payments-calendar-list';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getInstallments } from '@/lib/api/installments';
import { getPaymentObligations } from '@/lib/api/payment-obligations';
import { getPaymentsCalendar } from '@/lib/api/payments-calendar';
import { getPageSettings } from '@/lib/api/settings';
import { getSubscriptions } from '@/lib/api/subscriptions';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { resolveActiveCurrency } from '@/lib/stores/currency-store';
import { currentYearMonth } from '@/lib/utils/dates';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('paymentsCalendar');
}

interface PaymentsCalendarPageProps {
  searchParams: Promise<{
    year?: string;
    month?: string;
  }>;
}

export default async function PaymentsCalendarPage({ searchParams }: PaymentsCalendarPageProps) {
  const t = await getTranslations('paymentsCalendar');
  const params = await searchParams;
  const cookieStore = await cookies();

  const [{ settings, creditCards }, supportedCurrencies] = await Promise.all([
    getPageSettings(),
    // The linked-expense edit dialog restricts its currency picker to the convertible set; on a
    // fetch error the picker degrades to the full list and the API's 422 still guards.
    getSupportedCurrencies().catch(() => undefined),
  ]);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  const currency = resolveActiveCurrency(cookieStore, primary);

  // Default to the current month — resolved in the user's settings timezone — when the URL
  // doesn't carry year/month.
  const timeZone = settings?.timezone ?? undefined;
  const { year: nowYear, month: nowMonth } = currentYearMonth(timeZone);
  const year = parseYearMonth(params.year) ?? nowYear;
  const month = parseYearMonth(params.month) ?? nowMonth;

  // Round 2: the calendar plus the full plan lists (filtered below), one parallel round instead of
  // the previous calendar → plan-lists waterfall.
  const [calendar, allObligations, allSubscriptions, allInstallments] = await Promise.all([
    getPaymentsCalendar({ year, month, currency }),
    getPaymentObligations({ showArchived: true }).catch(() => []),
    getSubscriptions({ showArchived: true }).catch(() => []),
    getInstallments({ showArchived: true }).catch(() => []),
  ]);

  // Collect linked-plan source ids from paid calendar items so the inline-edit dialog can render
  // plan names for since-archived links. Only paid items are clickable → only their linked plans
  // need to be in scope; the filter reproduces the include_ids subset exactly.
  const linkedObligationIds = new Set(
    calendar.items.filter((i) => i.type === 'obligation' && i.isPaid).map((i) => i.sourceId),
  );
  const linkedSubscriptionIds = new Set(
    calendar.items.filter((i) => i.type === 'subscription' && i.isPaid).map((i) => i.sourceId),
  );
  const linkedInstallmentIds = new Set(
    calendar.items.filter((i) => i.type === 'installment' && i.isPaid).map((i) => i.sourceId),
  );

  const activeObligations = allObligations.filter(
    (o) => o.isActive || linkedObligationIds.has(o.id),
  );
  const activeSubscriptions = allSubscriptions.filter(
    (s) => s.isActive || linkedSubscriptionIds.has(s.id),
  );
  const activeInstallments = allInstallments.filter(
    (i) => i.isActive || linkedInstallmentIds.has(i.id),
  );

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <PaymentsCalendarHeader year={year} month={month} timeZone={timeZone} />
      <PaymentsCalendarList
        items={calendar.items}
        year={year}
        month={month}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        creditCards={creditCards}
        activeObligations={activeObligations}
        activeSubscriptions={activeSubscriptions}
        activeInstallments={activeInstallments}
        activeCurrency={currency}
        timeZone={timeZone}
      />
    </div>
  );
}

// Parses a query-string integer and ignores malformed values so the page falls
// back to "today" instead of crashing on garbage input.
function parseYearMonth(raw: string | undefined): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
