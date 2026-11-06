import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { SettingsFormFrame } from '@/app/(protected)/_components/settings-form-frame';
import { LocalizationForm } from '@/app/(protected)/localization/_components/localization-form';
import { UNSET_SETTINGS } from '@/lib/api/settings';

export default function LocalizationLoading() {
  return (
    <PageSkeleton
      namespace="localization"
      body="page"
      content={
        <SettingsFormFrame>
          <LocalizationForm initialSettings={UNSET_SETTINGS} />
        </SettingsFormFrame>
      }
    />
  );
}
