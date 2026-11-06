import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { NotificationsSections } from '@/app/(protected)/notifications/_components/notifications-sections';
import { getNotificationPreferences, getNotifications } from '@/lib/api/notifications';

/*
 * The page's own sections with its own reads (request-cached, shared with the page), so the feed has
 * the page's rows and the switches sit where they will. The first page of the feed: a loading state
 * cannot read `?page=`, and a later page is at most a page of rows shorter.
 */
export default async function NotificationsLoading() {
  const [feed, preferences] = await Promise.all([
    getNotifications(1).catch(() => null),
    getNotificationPreferences().catch(() => null),
  ]);

  return (
    <PageSkeleton
      namespace="notifications"
      body="page"
      content={<NotificationsSections feed={feed} preferences={preferences} page={1} />}
    />
  );
}
