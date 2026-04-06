import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { IntegrationsApiKeys } from '@/app/(protected)/integrations/_components/integrations-api-keys';
import { getApiKeys } from '@/lib/api/api-keys';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('integrations');
}

export default async function IntegrationsPage() {
  const t = await getTranslations('integrations');
  const apiKeys = await getApiKeys().catch(() => []);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <IntegrationsApiKeys initialKeys={apiKeys} />
    </div>
  );
}
