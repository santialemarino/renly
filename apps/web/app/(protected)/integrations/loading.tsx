import { PageSkeleton } from '@/app/(protected)/_components/page-skeleton';
import { IntegrationsSections } from '@/app/(protected)/integrations/_components/integrations-sections';
import { UNSET_SETTINGS } from '@/lib/api/settings';

// The page as an account without API keys sees it: a key list is data this state cannot know.
export default function IntegrationsLoading() {
  return (
    <PageSkeleton
      namespace="integrations"
      body="page"
      content={<IntegrationsSections apiKeys={[]} settings={UNSET_SETTINGS} />}
    />
  );
}
