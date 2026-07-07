import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { InvestmentsDataTable } from '@/app/(protected)/investments/_components/investments-data-table';
import { InvestmentsToolbar } from '@/app/(protected)/investments/_components/investments-toolbar';
import { SampleInvestmentsTable } from '@/app/(protected)/investments/_components/sample-investments-table';
import { getGroups, getInvestments } from '@/lib/api/investments';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('investments');
}

interface InvestmentsPageProps {
  searchParams: Promise<{
    search?: string;
    group_ids?: string | string[];
    category?: string;
    page?: string;
    sort_by?: string;
    sort_order?: string;
    show_archived?: string;
  }>;
}

export default async function InvestmentsPage({ searchParams }: InvestmentsPageProps) {
  const t = await getTranslations('investments');
  const params = await searchParams;

  const groupIdsRaw = params.group_ids;
  const groupIds = groupIdsRaw
    ? (Array.isArray(groupIdsRaw) ? groupIdsRaw : [groupIdsRaw]).map(Number).filter(Boolean)
    : undefined;

  const [data, groups, settings] = await Promise.all([
    getInvestments({
      search: params.search,
      groupIds,
      category: params.category,
      activeOnly: params.show_archived !== 'true',
      page: params.page ? Number(params.page) : 1,
      sortBy: params.sort_by as 'name' | 'category' | 'base_currency' | 'broker' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getGroups(),
    getSettings().catch(() => null),
  ]);

  const preferredCurrencies = settings?.preferredCurrencies ?? undefined;

  // Show this section's first-run sample only while it's empty; fetch the flag just then so a
  // populated section never pays for the extra read.
  const showSample =
    data.items.length === 0
      ? ((await getOnboardingStatus().catch(() => null))?.sampleInvestments ?? false)
      : false;

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <InvestmentsToolbar groups={groups} preferredCurrencies={preferredCurrencies} />
      {showSample ? (
        <SampleInvestmentsTable />
      ) : (
        <InvestmentsDataTable
          data={data}
          groups={groups}
          preferredCurrencies={preferredCurrencies}
        />
      )}
    </div>
  );
}
