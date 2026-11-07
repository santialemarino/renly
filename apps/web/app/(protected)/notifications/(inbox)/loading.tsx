import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { NotificationFeedSection } from '@/app/(protected)/notifications/_components/notification-feed-section';
import { getNotifications, type NotificationFeed } from '@/lib/api/notifications';
import { readForLoadingState } from '@/lib/utils/loading-state-read';

// What the loading state draws when the feed cannot be read in time: the empty inbox (the toolbar, then
// the empty state).
const EMPTY_FEED: NotificationFeed = { items: [], total: 0, pageSize: 1, unread: 0 };

/*
 * The page's own section with its own read (request-cached, shared with the page), so the rows sit
 * where they will. The first page of the feed: a loading state cannot read `?page=`, and a later page
 * is at most a page of rows shorter.
 */
export default async function NotificationsLoading() {
  const feed = await readForLoadingState(getNotifications(1), EMPTY_FEED);

  return (
    <PageSkeleton
      namespace="notifications"
      body="page"
      content={<NotificationFeedSection feed={feed} page={1} />}
    />
  );
}
