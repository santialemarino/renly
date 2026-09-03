import { getTranslations } from 'next-intl/server';

import { Separator } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { NotificationChannelsSection } from '@/app/(protected)/notifications/_components/notification-channels-section';
import { NotificationFeedSection } from '@/app/(protected)/notifications/_components/notification-feed-section';
import { PushSection } from '@/app/(protected)/notifications/_components/push-section';
import { getNotificationPreferences, getNotifications } from '@/lib/api/notifications';
import { NOTIFICATION_PAGE_SIZE } from '@/lib/constants/notifications';
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
  // Clamped rather than trusted: `?page=0` would ask for a negative offset and `?page=abc` for NaN,
  // and both are one hand-typed URL away.
  const parsed = Number(rawPage);
  const page = Number.isFinite(parsed) && parsed >= 1 ? Math.floor(parsed) : 1;

  const [feed, preferences] = await Promise.all([
    getNotifications(NOTIFICATION_PAGE_SIZE, (page - 1) * NOTIFICATION_PAGE_SIZE).catch(() => null),
    getNotificationPreferences().catch(() => null),
  ]);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex flex-col w-full max-w-3xl gap-y-8">
        {feed && <NotificationFeedSection key={page} feed={feed} page={page} />}
        {/* Each rule is conditional on BOTH sides of it, so a section that failed to load leaves no
            line hanging over nothing — the degraded page reads as a shorter page, not a broken one. */}
        {feed && preferences && <Separator />}
        {preferences && <NotificationChannelsSection initialPreferences={preferences} />}
        {preferences && <Separator />}
        {preferences && <PushSection initialPreferences={preferences} />}
      </div>
    </div>
  );
}
