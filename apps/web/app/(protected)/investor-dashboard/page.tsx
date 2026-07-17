import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { DashboardPeriodPicker } from '@/app/(protected)/_components/dashboard-period-picker';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import {
  InvestorDashboardAnimatedHeader,
  InvestorDashboardAnimatedToolbar,
} from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-animated-header';
import { InvestorDashboardDetailCard } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-detail-card';
import { InvestorDashboardDistribution } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-distribution';
import { InvestorDashboardEvolution } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-evolution';
import { InvestorDashboardMetricCards } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-metric-cards';
import { InvestorDashboardSearch } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-search';
import { InvestorDashboardSummaryTable } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-summary-table';
import { InvestorDashboardToolbar } from '@/app/(protected)/investor-dashboard/_components/investor-dashboard-toolbar';
import { DismissableCurrencyHint } from '@/components/dismissable-currency-hint';
import { DismissableHint } from '@/components/dismissable-hint';
import { InlineLink } from '@/components/inline-link';
import { WarningHint } from '@/components/styled-hint';
import { ROUTES } from '@/config/routes';
import { getGroups, getInvestments } from '@/lib/api/investments';
import {
  getAllocation,
  getAllocationByGroup,
  getInvestmentMetrics,
  getInvestmentsSummary,
  getPortfolioEvolution,
  getPortfolioMetrics,
  type MetricsFilterParams,
} from '@/lib/api/metrics';
import { getSettings } from '@/lib/api/settings';
import { API_MAX_PAGE_SIZE } from '@/lib/constants/api-constants';
import { FALLBACK_PRIMARY_CURRENCY } from '@/lib/constants/currency';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { todayInTimezone } from '@/lib/utils/dates';
import { generatePageMetadata } from '@/lib/utils/page-metadata';
import { buildPresets, presetToStartDate } from '@/lib/utils/period-presets';

export async function generateMetadata() {
  return await generatePageMetadata('investorDashboard');
}

interface InvestorDashboardPageProps {
  searchParams: Promise<{
    investment_id?: string;
    group_id?: string;
    category?: string;
    period?: string;
    start_date?: string;
    end_date?: string;
  }>;
}

export default async function InvestorDashboardPage({ searchParams }: InvestorDashboardPageProps) {
  const cookieStore = await cookies();
  const t = await getTranslations('investorDashboard');
  const tCommon = await getTranslations('common');
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

  // Parse filter params (singular from URL, wrapped in arrays for the API).
  const investmentIds = params.investment_id
    ? [Number(params.investment_id)].filter(Boolean)
    : undefined;
  const groupIds = params.group_id ? [Number(params.group_id)].filter(Boolean) : undefined;

  const category = params.category || undefined;

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

  const isSingleInvestment = investmentIds?.length === 1;
  const isFiltered = !!(investmentIds || groupIds || category);
  const isCategoryFilter = !!category && !investmentIds && !groupIds;
  const isGroupFilter = !!groupIds && !investmentIds && !category;

  // Build filter params.
  const filterParams: MetricsFilterParams = {
    currency,
    investmentIds,
    groupIds,
    category,
    startDate,
    endDate,
  };

  // Fetch all data in parallel.
  let metrics,
    evolution,
    categoryAllocation,
    groupAllocation,
    investmentsSummary,
    groups,
    investmentsList;
  try {
    [
      metrics,
      evolution,
      categoryAllocation,
      groupAllocation,
      investmentsSummary,
      groups,
      investmentsList,
    ] = await Promise.all([
      getPortfolioMetrics(filterParams),
      getPortfolioEvolution(filterParams),
      getAllocation(filterParams),
      getAllocationByGroup(filterParams),
      getInvestmentsSummary(filterParams),
      getGroups(),
      getInvestments({ activeOnly: true, pageSize: API_MAX_PAGE_SIZE }),
    ]);
  } catch {
    return (
      <div className="flex flex-col flex-1 p-8 gap-y-2">
        <PageHeader title={t('title')} subtitle={t('subtitle')} />
        <WarningHint show>{t('loadError')}</WarningHint>
      </div>
    );
  }

  // For single investment drill-down, fetch detailed metrics.
  const singleInvestmentId = isSingleInvestment ? investmentIds[0] : undefined;
  const investmentDetail = singleInvestmentId
    ? await getInvestmentMetrics(singleInvestmentId, currency).catch(() => null)
    : null;

  // Build subtitle based on filter context.
  let filterName: string | null = null;
  let subtitleKey = 'subtitle';
  if (isSingleInvestment && investmentDetail) {
    filterName = investmentDetail.name;
    subtitleKey = 'filtered.investment';
  } else if (groupIds?.length === 1) {
    const group = groups.find((g) => g.id === groupIds[0]);
    if (group) {
      filterName = group.name;
      subtitleKey = 'filtered.group';
    }
  } else if (category) {
    filterName = tCommon(`categories.${category}`);
    subtitleKey = 'filtered.category';
  } else if (isFiltered) {
    subtitleKey = 'filtered.subtitle';
  }

  // Build searchable investments list for the smart search.
  const searchableInvestments = investmentsList.items.map((inv: { id: number; name: string }) => ({
    id: inv.id,
    name: inv.name,
  }));

  // Collect skipped investments (same list from any endpoint — use metrics as source).
  const skippedInvestments = metrics.skippedInvestments;

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <InvestorDashboardAnimatedHeader
        subtitleKey={subtitleKey}
        subtitle={
          <PageHeader
            title={t('title')}
            subtitle={
              filterName
                ? t.rich(subtitleKey, {
                    name: filterName,
                    bold: (chunks) => <strong>{chunks}</strong>,
                  })
                : t(subtitleKey)
            }
          />
        }
        warnings={
          <>
            <WarningHint show={isOriginalSelected}>
              {t.rich('currencyFallback', {
                currency,
                bold: (chunks) => <strong>{chunks}</strong>,
              })}
            </WarningHint>
            <WarningHint show={skippedInvestments.length > 0}>
              {t('skippedInvestments', {
                names: skippedInvestments.map((s) => `${s.name} (${s.baseCurrency})`).join(', '),
              })}
            </WarningHint>
          </>
        }
      />
      <DismissableCurrencyHint show={!isOriginalSelected} />
      <InvestorDashboardAnimatedToolbar
        backButton={<InvestorDashboardToolbar isFiltered={isFiltered} />}
        search={<InvestorDashboardSearch investments={searchableInvestments} groups={groups} />}
        periodPicker={
          <DashboardPeriodPicker
            routePath={ROUTES.investorDashboard}
            translationNamespace="investorDashboard"
            presets={userPresets}
          />
        }
      />

      {/* Concept nudge explaining the return metrics; shown once the user has investments to measure. */}
      <DismissableHint storageKey="metrics-intro-dismissed" show={searchableInvestments.length > 0}>
        {t('metricsIntro')}{' '}
        <InlineLink href={`${ROUTES.help}#returns`} color="brand">
          {tCommon('learnMore')}
        </InlineLink>
      </DismissableHint>
      <InvestorDashboardMetricCards metrics={metrics} hasPeriod={Boolean(startDate || endDate)} />
      <InvestorDashboardEvolution evolution={evolution} />

      {isSingleInvestment && investmentDetail ? (
        <InvestorDashboardDetailCard metrics={investmentDetail} />
      ) : (
        <div className="flex flex-col gap-6 lg:flex-row">
          <InvestorDashboardDistribution
            categoryAllocation={categoryAllocation}
            groupAllocation={groupAllocation}
            forcedMode={isCategoryFilter ? 'group' : isGroupFilter ? 'category' : undefined}
          />
          <InvestorDashboardSummaryTable summary={investmentsSummary} />
        </div>
      )}
    </div>
  );
}
