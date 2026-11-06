import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { AlertsForm } from '@/app/(protected)/alerts/_components/alerts-form';
import { UNSET_SETTINGS } from '@/lib/api/settings';

export default function AlertsLoading() {
  return (
    <PageSkeleton
      namespace="alerts"
      body="page"
      content={
        <SettingsFormFrame>
          <AlertsForm initialSettings={UNSET_SETTINGS} />
        </SettingsFormFrame>
      }
    />
  );
}
