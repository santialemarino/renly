import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { PreferencesForm } from '@/app/(protected)/preferences/_components/preferences-form';
import { getSettings, UNSET_SETTINGS } from '@/lib/api/settings';

// The form with the user's own settings (the layout's request-cached read), so it wraps as the page will.
export default async function PreferencesLoading() {
  const settings = await getSettings().catch(() => UNSET_SETTINGS);

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
