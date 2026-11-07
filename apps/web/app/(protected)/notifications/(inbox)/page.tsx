import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { NotificationFeedSection } from '@/app/(protected)/notifications/_components/notification-feed-section';
import { getNotifications } from '@/lib/api/notifications';
import { resolvePageParam } from '@/lib/list-scope';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('notifications');
}

interface NotificationsPageProps {
  searchParams: Promise<{ page?: string }>;
}

/*
 * The inbox: every notification, newest first. Reached from the bell's "See all" and from every link
 * that says "your notifications" (the daily digest's), and deliberately NOT from the sidebar — its
 * Settings item opens the notification settings, which this page links to from its own toolbar.
 *
 * The feed is the page, so its read is awaited bare: an empty list after a failed read would claim
 * nothing ever happened.
 */
export default async function NotificationsPage({ searchParams }: NotificationsPageProps) {
  const t = await getTranslations('notifications');
  const { page: rawPage } = await searchParams;
  const page = resolvePageParam(rawPage);

  const feed = await getNotifications(page);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <NotificationFeedSection key={page} feed={feed} page={page} />
    </div>
  );
}
