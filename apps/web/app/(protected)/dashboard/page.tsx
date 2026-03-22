import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { DistributionSection } from '@/app/(protected)/dashboard/_components/distribution-section';
import { EvolutionSection } from '@/app/(protected)/dashboard/_components/evolution-section';
import { InvestmentsSummaryTable } from '@/app/(protected)/dashboard/_components/investments-summary-table';
import { MetricCards } from '@/app/(protected)/dashboard/_components/metric-cards';
import { WarningHint } from '@/components/warning-hint';
import {
  getAllocation,
  getAllocationByGroup,
  getInvestmentsSummary,
  getPortfolioEvolution,
  getPortfolioMetrics,
} from '@/lib/api/metrics';
import { getSettings } from '@/lib/api/settings';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

const FALLBACK_PRIMARY = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';

export async function generateMetadata() {
  return await generatePageMetadata('dashboard');
}

export default async function DashboardPage() {
  const cookieStore = await cookies();
  const t = await getTranslations('dashboard');

  const activeCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;

  // Aggregated portfolio metrics need a common currency to be meaningful.
  // When "Original" is selected, fall back to the user's primary currency.
  const isOriginalSelected = activeCurrency === ORIGINAL_CURRENCY;

  // Aggregated portfolio metrics need a common currency to be meaningful.
  // When "Original" is selected, fall back to the user's primary currency.
  let currency: string;
  if (!isOriginalSelected) {
    currency = activeCurrency;
  } else {
    const settings = await getSettings().catch(() => null);
    currency = settings?.primaryCurrency ?? FALLBACK_PRIMARY;
  }

  const [metrics, evolution, categoryAllocation, groupAllocation, investmentsSummary] =
    await Promise.all([
      getPortfolioMetrics(currency),
      getPortfolioEvolution(currency),
      getAllocation(currency),
      getAllocationByGroup(currency),
      getInvestmentsSummary(currency),
    ]);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <div className="flex flex-col gap-y-1">
        <PageHeader title={t('title')} subtitle={t('subtitle')} />
        <WarningHint show={isOriginalSelected}>
          {t.rich('currencyFallback', { currency, bold: (chunks) => <strong>{chunks}</strong> })}
        </WarningHint>
      </div>
      <MetricCards metrics={metrics} />
      <EvolutionSection evolution={evolution} />
      <div className="flex flex-col gap-6 lg:flex-row">
        <DistributionSection
          categoryAllocation={categoryAllocation}
          groupAllocation={groupAllocation}
        />
        <InvestmentsSummaryTable summary={investmentsSummary} />
      </div>
    </div>
  );
}
