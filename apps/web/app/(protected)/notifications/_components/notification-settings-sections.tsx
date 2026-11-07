import { Separator } from '@repo/ui/components';
import { NotificationChannelsSection } from '@/app/(protected)/notifications/_components/notification-channels-section';
import { PushSection } from '@/app/(protected)/notifications/_components/push-section';
import type { NotificationPreferences } from '@/lib/api/notifications';

interface NotificationSettingsSectionsProps {
  preferences: NotificationPreferences;
}

// The notification settings page's sections under its header — rendered by the page, and as its
// placeholder by its loading state.
export function NotificationSettingsSections({ preferences }: NotificationSettingsSectionsProps) {
  return (
    <div className="flex flex-col w-full max-w-3xl gap-y-8">
      <NotificationChannelsSection initialPreferences={preferences} />
      <Separator />
      <PushSection initialPreferences={preferences} />
    </div>
  );
}
