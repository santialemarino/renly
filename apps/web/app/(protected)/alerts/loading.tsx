import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { AlertsForm } from '@/app/(protected)/alerts/_components/alerts-form';
import { getSettings, UNSET_SETTINGS } from '@/lib/api/settings';

// The form with the user's own settings (the layout's request-cached read), so it is the page's shape.
export default async function AlertsLoading() {
  const settings = await getSettings().catch(() => UNSET_SETTINGS);

  return (
    <PageSkeleton
      namespace="alerts"
      body="page"
      content={
        <SettingsFormFrame>
          <AlertsForm initialSettings={settings} />
        </SettingsFormFrame>
      }
    />
  );
}
