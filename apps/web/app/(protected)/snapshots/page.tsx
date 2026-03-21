import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { SnapshotsGrid } from '@/app/(protected)/snapshots/_components/snapshots-grid';
import { SnapshotsToolbar } from '@/app/(protected)/snapshots/_components/snapshots-toolbar';
import { getGroups } from '@/lib/api/investments';
import { getSnapshotGrid } from '@/lib/api/snapshots';
import { generatePageMetadata } from '@/lib/utils/page';

export async function generateMetadata() {
  return await generatePageMetadata('snapshots');
}

interface SnapshotsPageProps {
  searchParams: Promise<{
    search?: string;
    group_ids?: string | string[];
    category?: string;
  }>;
}

export default async function SnapshotsPage({ searchParams }: SnapshotsPageProps) {
  const t = await getTranslations('snapshots');
  const params = await searchParams;

  const groupIdsRaw = params.group_ids;
  const groupIds = groupIdsRaw
    ? (Array.isArray(groupIdsRaw) ? groupIdsRaw : [groupIdsRaw]).map(Number).filter(Boolean)
    : undefined;

  const [grid, groups] = await Promise.all([
    getSnapshotGrid({
      search: params.search,
      groupIds,
      category: params.category,
    }),
    getGroups(),
  ]);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <SnapshotsToolbar groups={groups} />
      <SnapshotsGrid grid={grid} />
    </div>
  );
}
