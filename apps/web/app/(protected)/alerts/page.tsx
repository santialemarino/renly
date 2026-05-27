import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { AlertsForm } from '@/app/(protected)/alerts/_components/alerts-form';
import { getSettings } from '@/lib/api/settings';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('alerts');
}

export default async function AlertsPage() {
  const t = await getTranslations('alerts');
  const settings = await getSettings().catch(() => null);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <div className="flex w-full justify-center lg:justify-start">
        {settings && <AlertsForm initialSettings={settings} />}
      </div>
    </div>
  );
}
