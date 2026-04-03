import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { GroupsDataTable } from '@/app/(protected)/groups/_components/groups-data-table';
import { GroupsToolbar } from '@/app/(protected)/groups/_components/groups-toolbar';
import { getGroups } from '@/lib/api/groups';
import { getInvestments } from '@/lib/api/investments';
import { getSettings } from '@/lib/api/settings';
import { API_MAX_PAGE_SIZE } from '@/lib/constants/api-constants';
import { ENV_GROUP_WARNING_PCT, ENV_MAX_GROUPS } from '@/lib/constants/groups';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('groups');
}

interface GroupsPageProps {
  searchParams: Promise<{
    search?: string;
    sort_by?: string;
    sort_order?: string;
  }>;
}

export default async function GroupsPage({ searchParams }: GroupsPageProps) {
  const t = await getTranslations('groups');
  const params = await searchParams;

  const [groups, allGroups, investmentsList, settings] = await Promise.all([
    getGroups({
      search: params.search,
      sortBy: params.sort_by as 'name' | undefined,
      sortOrder: params.sort_order as 'asc' | 'desc' | undefined,
    }),
    getGroups(),
    getInvestments({ activeOnly: true, pageSize: API_MAX_PAGE_SIZE }),
    getSettings().catch(() => null),
  ]);

  const investments = investmentsList.items.map((inv) => ({ id: inv.id, name: inv.name }));
  const maxGroups = settings?.maxGroups ?? ENV_MAX_GROUPS;
  const groupWarningPct = settings?.groupWarningPct ?? ENV_GROUP_WARNING_PCT;

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <GroupsToolbar
        investments={investments}
        groupCount={allGroups.length}
        maxGroups={maxGroups}
        groupWarningPct={groupWarningPct}
      />
      <GroupsDataTable
        groups={groups}
        investments={investments}
        sortBy={params.sort_by}
        sortOrder={params.sort_order as 'asc' | 'desc' | undefined}
      />
    </div>
  );
}
