import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import {
  AnimatedDashboardHeader,
  AnimatedDashboardToolbar,
} from '@/app/(protected)/dashboard/_components/animated-dashboard-header';
import { DashboardSearch } from '@/app/(protected)/dashboard/_components/dashboard-search';
import { DashboardToolbar } from '@/app/(protected)/dashboard/_components/dashboard-toolbar';
import { DistributionSection } from '@/app/(protected)/dashboard/_components/distribution-section';
import { EvolutionSection } from '@/app/(protected)/dashboard/_components/evolution-section';
import { InvestmentDetailCard } from '@/app/(protected)/dashboard/_components/investment-detail-card';
import { InvestmentsSummaryTable } from '@/app/(protected)/dashboard/_components/investments-summary-table';
import { MetricCards } from '@/app/(protected)/dashboard/_components/metric-cards';
import { PeriodPicker } from '@/app/(protected)/dashboard/_components/period-picker';
import { WarningHint } from '@/components/styled-hint';
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
import { buildPresets, presetToStartDate } from '@/lib/constants/period-presets';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

const FALLBACK_PRIMARY = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';

export async function generateMetadata() {
  return await generatePageMetadata('dashboard');
}

interface DashboardPageProps {
  searchParams: Promise<{
    investment_id?: string;
    group_id?: string;
    category?: string;
    period?: string;
    start_date?: string;
    end_date?: string;
  }>;
}

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  const cookieStore = await cookies();
  const t = await getTranslations('dashboard');
  const tCommon = await getTranslations('common');
  const params = await searchParams;

  const activeCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;

  // Always fetch settings — needed for currency fallback and period presets.
  const settings = await getSettings().catch(() => null);
  const isOriginalSelected = activeCurrency === ORIGINAL_CURRENCY;
  const currency = isOriginalSelected
    ? (settings?.primaryCurrency ?? FALLBACK_PRIMARY)
    : activeCurrency;
  const userPresets = buildPresets(settings?.periodPresets);

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
    startDate = presetToStartDate(period);
    endDate = new Date().toISOString().slice(0, 10);
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
      <AnimatedDashboardHeader
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
      <AnimatedDashboardToolbar
        backButton={<DashboardToolbar isFiltered={isFiltered} />}
        search={<DashboardSearch investments={searchableInvestments} groups={groups} />}
        periodPicker={<PeriodPicker presets={userPresets} />}
      />

      <MetricCards metrics={metrics} />
      <EvolutionSection evolution={evolution} />

      {isSingleInvestment && investmentDetail ? (
        <InvestmentDetailCard metrics={investmentDetail} />
      ) : (
        <div className="flex flex-col gap-6 lg:flex-row">
          <DistributionSection
            categoryAllocation={categoryAllocation}
            groupAllocation={groupAllocation}
            forcedMode={isCategoryFilter ? 'group' : isGroupFilter ? 'category' : undefined}
          />
          <InvestmentsSummaryTable summary={investmentsSummary} />
        </div>
      )}
    </div>
  );
}
