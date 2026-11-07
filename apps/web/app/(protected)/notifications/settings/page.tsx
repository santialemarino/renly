import { getTranslations } from 'next-intl/server';

import { Separator } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { NotificationChannelsSection } from '@/app/(protected)/notifications/_components/notification-channels-section';
import { PushSection } from '@/app/(protected)/notifications/_components/push-section';
import { getNotificationPreferences } from '@/lib/api/notifications';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('notifications.settings');
}

/*
 * What Renly tells you about and where it reaches you: the events x channels grid with the email
 * cadence, then web push for this browser. The Settings group's Notifications item opens it; the inbox
 * links here from its toolbar.
 *
 * The preferences are the page, so their read is awaited bare: every switch rendered "off" after a
 * failed read would state a choice nobody made.
 */
export default async function NotificationSettingsPage() {
  const t = await getTranslations('notifications.settings');

  const preferences = await getNotificationPreferences();

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex flex-col w-full max-w-3xl gap-y-8">
        <NotificationChannelsSection initialPreferences={preferences} />
        <Separator />
        <PushSection initialPreferences={preferences} />
      </div>
    </div>
  );
}
