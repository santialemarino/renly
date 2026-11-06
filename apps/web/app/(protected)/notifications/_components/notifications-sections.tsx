import { Separator } from '@repo/ui/components';
import { NotificationChannelsSection } from '@/app/(protected)/notifications/_components/notification-channels-section';
import { NotificationFeedSection } from '@/app/(protected)/notifications/_components/notification-feed-section';
import { PushSection } from '@/app/(protected)/notifications/_components/push-section';
import type { NotificationFeed, NotificationPreferences } from '@/lib/api/notifications';

interface NotificationsSectionsProps {
  // Either read may have failed; its section is then left out.
  feed: NotificationFeed | null;
  preferences: NotificationPreferences | null;
  page: number;
}

// The notifications page's sections under its header — rendered by the page, and as its placeholder
// by its loading state.
export function NotificationsSections({ feed, preferences, page }: NotificationsSectionsProps) {
  return (
    <div className="flex flex-col w-full max-w-3xl gap-y-8">
      {feed && <NotificationFeedSection key={page} feed={feed} page={page} />}
      {/* Each rule is conditional on BOTH sides of it, so a section that failed to load leaves no
          line hanging over nothing — the degraded page reads as a shorter page, not a broken one. */}
      {feed && preferences && <Separator />}
      {preferences && <NotificationChannelsSection initialPreferences={preferences} />}
      {preferences && <Separator />}
      {preferences && <PushSection initialPreferences={preferences} />}
    </div>
  );
}
