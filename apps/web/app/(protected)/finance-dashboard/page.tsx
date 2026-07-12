import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { DashboardPeriodPicker } from '@/app/(protected)/_components/dashboard-period-picker';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { FinanceDashboardDistribution } from '@/app/(protected)/finance-dashboard/_components/finance-dashboard-distribution';
import { FinanceDashboardMetricCards } from '@/app/(protected)/finance-dashboard/_components/finance-dashboard-metric-cards';
import { FinanceDashboardMonthlyChart } from '@/app/(protected)/finance-dashboard/_components/finance-dashboard-monthly-chart';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { WarningHint } from '@/components/styled-hint';
import { ROUTES } from '@/config/routes';
import {
  getExpenseBreakdown,
  getFinanceMonthly,
  getFinanceOverview,
  getIncomeBreakdown,
  type FinanceMetricsFilterParams,
} from '@/lib/api/finance-metrics';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { todayInTimezone } from '@/lib/utils/dates';
import { generatePageMetadata } from '@/lib/utils/page-metadata';
import { buildPresets, presetToStartDate } from '@/lib/utils/period-presets';

export async function generateMetadata() {
  return await generatePageMetadata('financeDashboard');
}

interface FinanceDashboardPageProps {
  searchParams: Promise<{
    period?: string;
    start_date?: string;
    end_date?: string;
  }>;
}

export default async function FinanceDashboardPage({ searchParams }: FinanceDashboardPageProps) {
  const cookieStore = await cookies();
  const t = await getTranslations('financeDashboard');
  const params = await searchParams;

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;

  // Always fetch settings — needed for currency fallback and period presets.
  const settings = await getSettings().catch(() => null);
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const secondary = settings?.secondaryCurrency ?? null;
  const displayCurrencies = secondary
    ? [primary, secondary, ORIGINAL_CURRENCY]
    : [primary, ORIGINAL_CURRENCY];

  // Validate saved cookie against current settings — fall back to primary if stale.
  const activeCurrency =
    savedCurrency && displayCurrencies.includes(savedCurrency) ? savedCurrency : primary;
  const isOriginalSelected = activeCurrency === ORIGINAL_CURRENCY;
  const currency = isOriginalSelected ? primary : activeCurrency;
  const userPresets = buildPresets(settings?.periodPresets);
  // User-tz "today": period boundaries resolve in the user's settings timezone.
  const timeZone = settings?.timezone ?? undefined;

  // Parse date range from period presets or explicit dates.
  const period = params.period;
  let startDate: string | undefined;
  let endDate: string | undefined;

  if (params.start_date) {
    startDate = params.start_date;
    endDate = params.end_date;
  } else if (period && period !== 'all') {
    startDate = presetToStartDate(period, timeZone);
    endDate = todayInTimezone(timeZone);
  }

  // Build filter params.
  const filterParams: FinanceMetricsFilterParams = {
    currency,
    dateFrom: startDate,
    dateTo: endDate,
  };

  // Fetch all data in parallel.
  let overview, monthly, expenseBreakdown, incomeBreakdown;
  try {
    [overview, monthly, expenseBreakdown, incomeBreakdown] = await Promise.all([
      getFinanceOverview(filterParams),
      getFinanceMonthly(filterParams),
      getExpenseBreakdown(filterParams),
      getIncomeBreakdown(filterParams),
    ]);
  } catch {
    return (
      <div className="flex flex-col flex-1 p-8 gap-y-2">
        <PageHeader title={t('title')} subtitle={t('subtitle')} />
        <WarningHint show>{t('loadError')}</WarningHint>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <div className="flex flex-col gap-y-4 sm:flex-row sm:items-start sm:justify-between">
        <PageHeader title={t('title')} subtitle={t('subtitle')} />
        <DashboardPeriodPicker
          routePath={ROUTES.financeDashboard}
          translationNamespace="financeDashboard"
          presets={userPresets}
          className="sm:max-w-md"
        />
      </div>

      <DismissableCurrencyHint show={!isOriginalSelected} />
      <WarningHint show={isOriginalSelected}>
        {t.rich('currencyFallback', {
          currency,
          bold: (chunks) => <strong>{chunks}</strong>,
        })}
      </WarningHint>

      <FinanceDashboardMetricCards overview={overview} />
      <FinanceDashboardMonthlyChart monthly={monthly} />
      <FinanceDashboardDistribution
        expenseBreakdown={expenseBreakdown}
        incomeBreakdown={incomeBreakdown}
      />
    </div>
  );
}
