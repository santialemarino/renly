import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { PreferencesForm } from '@/app/(protected)/preferences/_components/preferences-form';
import { getSettings, UNSET_SETTINGS } from '@/lib/api/settings';
import { readForLoadingState } from '@/lib/utils/loading-state-read';

// The form with the user's own settings (the layout's request-cached read), so it wraps as the page will.
export default async function PreferencesLoading() {
  const settings = await readForLoadingState(getSettings(), UNSET_SETTINGS);

  return (
    <PageSkeleton
      namespace="preferences"
      body="page"
      content={
        <SettingsFormFrame>
          <PreferencesForm initialSettings={settings} supportedCurrencies={undefined} />
        </SettingsFormFrame>
      }
    />
  );
}
