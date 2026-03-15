import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { SettingsForm } from '@/app/(protected)/settings/_components/settings-form';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page';

export async function generateMetadata() {
  return await generatePageMetadata('settings');
}

export default async function SettingsPage() {
  const t = await getTranslations('settings');
  const settings = await getSettings().catch(() => null);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-6">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      {settings && <SettingsForm initialSettings={settings} />}
    </div>
  );
}
