import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { NotificationSettingsSections } from '@/app/(protected)/notifications/_components/notification-settings-sections';
import { getNotificationPreferences, type NotificationPreferences } from '@/lib/api/notifications';
import { readForLoadingState } from '@/lib/utils/loading-state-read';

/*
 * What the loading state draws when the preferences cannot be read in time. The grid is built from the
 * event and channel lists rather than from these rows, so it keeps its shape with none; push is drawn
 * as available, which is the deployment's normal state.
 */
const UNSET_PREFERENCES: NotificationPreferences = {
  preferences: [],
  emailCadence: 'immediate',
  pushAvailable: true,
  pushPublicKey: null,
  pushSubscriptions: 0,
};

// The page's own sections with its own read (request-cached, shared with the page).
export default async function NotificationSettingsLoading() {
  const preferences = await readForLoadingState(getNotificationPreferences(), UNSET_PREFERENCES);

  return (
    <PageSkeleton
      namespace="notifications.settings"
      body="page"
      content={<NotificationSettingsSections preferences={preferences} />}
    />
  );
}
