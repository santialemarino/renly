import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { LocalizationForm } from '@/app/(protected)/localization/_components/localization-form';
import { getSettings, UNSET_SETTINGS } from '@/lib/api/settings';

// The form with the user's own settings (the layout's request-cached read): a manual mode changes
// the hints, and so the wrapping.
export default async function LocalizationLoading() {
  const settings = await getSettings().catch(() => UNSET_SETTINGS);

  return (
    <PageSkeleton
      namespace="localization"
      body="page"
      content={
        <SettingsFormFrame>
          <LocalizationForm initialSettings={settings} />
        </SettingsFormFrame>
      }
    />
  );
}
