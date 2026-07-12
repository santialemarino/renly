import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { DashboardPeriodPicker } from '@/app/(protected)/_components/dashboard-period-picker';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { DashboardComposition } from '@/app/(protected)/dashboard/_components/dashboard-composition';
import { DashboardEvolutionChart } from '@/app/(protected)/dashboard/_components/dashboard-evolution';
import { DashboardFooter } from '@/app/(protected)/dashboard/_components/dashboard-footer';
import { DashboardMetricCards } from '@/app/(protected)/dashboard/_components/dashboard-metric-cards';
import { OnboardingWelcome } from '@/app/(protected)/dashboard/_components/onboarding-welcome';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { WarningHint } from '@/components/styled-hint';
import { ROUTES } from '@/config/routes';
import {
  getDashboardComposition,
  getDashboardEvolution,
  getDashboardLiquidity,
  getDashboardOverview,
  type DashboardFilterParams,
} from '@/lib/api/dashboard';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import {
  ENV_INCOME_EXPENSE_RATIO_HEALTHY,
  ENV_SAVINGS_RATE_HEALTHY_PCT,
  ENV_SAVINGS_RATE_MODERATE_PCT,
} from '@/lib/constants/health-thresholds';
import { hasNoCoreData } from '@/lib/onboarding';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { todayInTimezone } from '@/lib/utils/dates';
import { generatePageMetadata } from '@/lib/utils/page-metadata';
import { buildPresets, presetToStartDate } from '@/lib/utils/period-presets';

export async function generateMetadata() {
  return await generatePageMetadata('dashboard');
}

interface DashboardPageProps {
  searchParams: Promise<{
    period?: string;
    start_date?: string;
    end_date?: string;
  }>;
}

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  const cookieStore = await cookies();
  const t = await getTranslations('dashboard');
  const params = await searchParams;

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;

  // Always fetch settings — needed for currency fallback and period presets.
  const settings = await getSettings().catch(() => null);

  // The first-run welcome only shows until onboarding is dismissed/completed; fetch its checklist
  // status only in that window so returning users don't pay for the extra read.
  const showWelcome = Boolean(settings) && !settings?.onboardingCompleted;
  const onboardingStatus = showWelcome ? await getOnboardingStatus().catch(() => null) : null;

  // Auto-launch the welcome tour once for a first-run newcomer who hasn't seen it — the shared
  // no-core-data signal UX-7 uses for the reduced sidebar, plus the dedicated tour flag. Rides the
  // status already fetched for the checklist, so it costs no extra request.
  const autoStartTour = hasNoCoreData(onboardingStatus) && !onboardingStatus?.tourCompleted;
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
  const filterParams: DashboardFilterParams = {
    currency,
    dateFrom: startDate,
    dateTo: endDate,
  };

  // Fetch all data in parallel.
  let overview, evolution, composition, liquidity;
  try {
    [overview, evolution, composition, liquidity] = await Promise.all([
      getDashboardOverview(filterParams),
      getDashboardEvolution(filterParams),
      getDashboardComposition({ currency }),
      getDashboardLiquidity({ currency }),
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
          routePath={ROUTES.dashboard}
          translationNamespace="dashboard"
          presets={userPresets}
          className="sm:max-w-md"
        />
      </div>

      {showWelcome && <OnboardingWelcome status={onboardingStatus} autoStartTour={autoStartTour} />}

      <DismissableCurrencyHint show={!isOriginalSelected} />
      <WarningHint show={isOriginalSelected}>
        {t.rich('currencyFallback', {
          currency,
          bold: (chunks) => <strong>{chunks}</strong>,
        })}
      </WarningHint>

      <DashboardMetricCards overview={overview} />

      <div className="flex flex-col gap-6 lg:flex-row">
        <DashboardEvolutionChart evolution={evolution} />
        <DashboardComposition composition={composition.items} />
      </div>

      <DashboardFooter
        overview={overview}
        liquidity={liquidity}
        savingsRateHealthyPct={settings?.savingsRateHealthyPct ?? ENV_SAVINGS_RATE_HEALTHY_PCT}
        savingsRateModeratePct={settings?.savingsRateModeratePct ?? ENV_SAVINGS_RATE_MODERATE_PCT}
        incomeExpenseRatioHealthy={
          settings?.incomeExpenseRatioHealthy ?? ENV_INCOME_EXPENSE_RATIO_HEALTHY
        }
      />
    </div>
  );
}
