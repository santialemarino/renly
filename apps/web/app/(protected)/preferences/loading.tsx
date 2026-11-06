import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { PreferencesForm } from '@/app/(protected)/preferences/_components/preferences-form';
import { UNSET_SETTINGS } from '@/lib/api/settings';

export default function PreferencesLoading() {
  return (
    <PageSkeleton
      namespace="preferences"
      body="page"
      content={
        <SettingsFormFrame>
          <PreferencesForm initialSettings={UNSET_SETTINGS} supportedCurrencies={undefined} />
        </SettingsFormFrame>
      }
    />
  );
}
