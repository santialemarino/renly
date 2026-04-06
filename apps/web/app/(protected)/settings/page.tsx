import { getTranslations } from 'next-intl/server';

import { Separator } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { SettingsApiKeys } from '@/app/(protected)/settings/_components/settings-api-keys';
import { SettingsForm } from '@/app/(protected)/settings/_components/settings-form';
import { getApiKeys } from '@/lib/api/api-keys';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('settings');
}

export default async function SettingsPage() {
  const t = await getTranslations('settings');
  const [settings, apiKeys] = await Promise.all([
    getSettings().catch(() => null),
    getApiKeys().catch(() => []),
  ]);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex w-full justify-center lg:justify-start">
        {settings && <SettingsForm initialSettings={settings} />}
      </div>
      <Separator className="my-2" />
      <SettingsApiKeys initialKeys={apiKeys} />
    </div>
  );
}
