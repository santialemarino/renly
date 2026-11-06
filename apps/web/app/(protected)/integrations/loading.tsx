import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { IntegrationsSections } from '@/app/(protected)/integrations/_components/integrations-sections';
import { getApiKeys } from '@/lib/api/api-keys';
import { getSettings, type SettingsData } from '@/lib/api/settings';
import { readForLoadingState } from '@/lib/utils/loading-state-read';

// The page's own reads (request-cached, shared with the page), so the key list has the page's rows.
export default async function IntegrationsLoading() {
  const [apiKeys, settings] = await Promise.all([
    readForLoadingState(getApiKeys(), []),
    readForLoadingState<SettingsData | null>(getSettings(), null),
  ]);

  return (
    <PageSkeleton
      namespace="integrations"
      body="page"
      content={<IntegrationsSections apiKeys={apiKeys} settings={settings} />}
    />
  );
}
