import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { GroupsTable } from '@/app/(protected)/shared/_components/groups-table';
import { GroupsToolbar } from '@/app/(protected)/shared/_components/groups-toolbar';
import { getGroups } from '@/lib/api/groups';
import { getSettings } from '@/lib/api/settings';
import { isFirstRunEmptyState } from '@/lib/onboarding';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('shared');
}

export default async function SharedGroupsPage() {
  const t = await getTranslations('shared');

  // getSettings, not getPageSettings: this page needs no credit cards, and the bundled helper
  // would fetch them anyway.
  const [groups, settings] = await Promise.all([getGroups(), getSettings().catch(() => null)]);

  // Teach the empty state only during first-run. There is no filter on this page, so the second
  // argument is always false — nothing can be hiding rows that exist.
  const firstRun = isFirstRunEmptyState(groups.length === 0, false, settings);

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <GroupsToolbar />
      <GroupsTable groups={groups} firstRun={firstRun} />
    </div>
  );
}
