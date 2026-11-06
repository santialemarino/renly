import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { NotificationsSections } from '@/app/(protected)/notifications/_components/notifications-sections';
import { getNotificationPreferences, getNotifications } from '@/lib/api/notifications';
import { resolvePageParam } from '@/lib/list-scope';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('notifications');
}

interface NotificationsPageProps {
  searchParams: Promise<{ page?: string }>;
}

/*
 * One page for the whole subject, three sections split by a Separator — the shape /data and /account
 * already use. The FEED comes first because both ways in land here: the bell's "See all" and the
 * Settings item, and a list is what most visits are for.
 *
 * Both reads fail soft. A feed that cannot load must not take the switches down with it, and vice
 * versa: they are separate concerns that share a page, and half a page is better than a crash on a
 * surface whose whole job is telling you things.
 */
export default async function NotificationsPage({ searchParams }: NotificationsPageProps) {
  const t = await getTranslations('notifications');
  const { page: rawPage } = await searchParams;
  const page = resolvePageParam(rawPage);

  const [feed, preferences] = await Promise.all([
    getNotifications(page).catch(() => null),
    getNotificationPreferences().catch(() => null),
  ]);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <NotificationsSections feed={feed} preferences={preferences} page={page} />
    </div>
  );
}
