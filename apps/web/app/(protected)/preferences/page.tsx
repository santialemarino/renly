import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { PreferencesForm } from '@/app/(protected)/preferences/_components/preferences-form';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('preferences');
}

export default async function PreferencesPage() {
  const t = await getTranslations('preferences');
  const settings = await getSettings().catch(() => null);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex w-full justify-center lg:justify-start">
        {settings && <PreferencesForm initialSettings={settings} />}
      </div>
    </div>
  );
}
