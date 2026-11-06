import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { LocalizationForm } from '@/app/(protected)/localization/_components/localization-form';
import { getSettings, UNSET_SETTINGS } from '@/lib/api/settings';
import { readForLoadingState } from '@/lib/utils/loading-state-read';

// The form with the user's own settings (the layout's request-cached read): a manual mode changes
// the hints, and so the wrapping.
export default async function LocalizationLoading() {
  const settings = await readForLoadingState(getSettings(), UNSET_SETTINGS);

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
