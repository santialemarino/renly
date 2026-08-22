import { notFound } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { GroupHubHeader } from '@/app/(protected)/shared/[groupId]/_components/group-hub-header';
import { GroupMembersSection } from '@/app/(protected)/shared/[groupId]/_components/group-members-section';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { getGroup } from '@/lib/api/groups';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

// Its own namespace rather than the list's, so a hub tab isn't titled "Groups".
export async function generateMetadata() {
  return await generatePageMetadata('shared.hub');
}

interface GroupHubPageProps {
  params: Promise<{ groupId: string }>;
}

export default async function GroupHubPage({ params }: GroupHubPageProps) {
  const t = await getTranslations('shared');
  const { groupId } = await params;

  // A non-numeric segment never reaches the API — `/shared/nonsense` is a 404, not a 422.
  const id = Number(groupId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  // Null covers both "no such group" and "one you are not a member of", so the page's answer is
  // identical either way and cannot be used to probe which groups exist.
  const group = await getGroup(id);
  if (!group) notFound();

  return (
    <div className="flex flex-col flex-1 p-8 gap-y-6">
      <InlineLink href={ROUTES.shared} color="muted" icon={ArrowLeft}>
        {t('hub.back')}
      </InlineLink>
      <GroupHubHeader group={group} />
      <GroupMembersSection group={group} />
    </div>
  );
}
