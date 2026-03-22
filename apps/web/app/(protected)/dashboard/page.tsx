import { cookies } from 'next/headers';
import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { EvolutionSection } from '@/app/(protected)/dashboard/_components/evolution-section';
import { MetricCards } from '@/app/(protected)/dashboard/_components/metric-cards';
import { getPortfolioEvolution, getPortfolioMetrics } from '@/lib/api/metrics';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('dashboard');
}

export default async function DashboardPage() {
  const cookieStore = await cookies();
  const t = await getTranslations('dashboard');

  const activeCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? ORIGINAL_CURRENCY;
  const currency = activeCurrency !== ORIGINAL_CURRENCY ? activeCurrency : undefined;

  const [metrics, evolution] = await Promise.all([
    getPortfolioMetrics(currency),
    getPortfolioEvolution(currency),
  ]);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <MetricCards metrics={metrics} />
      <EvolutionSection evolution={evolution} />
    </div>
  );
}
