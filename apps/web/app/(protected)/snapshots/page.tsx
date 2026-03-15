import { getTranslations } from 'next-intl/server';

import { generatePageMetadata } from '@/lib/utils/page';

export async function generateMetadata() {
  return await generatePageMetadata('snapshots');
}

export default async function SnapshotsPage() {
  const t = await getTranslations('snapshots');

  return (
    <div className="flex flex-col flex-1 items-center justify-center p-8 gap-y-2">
      <h1 className="text-heading-3 text-foreground">{t('title')}</h1>
      <p className="text-muted-foreground">{t('subtitle')}</p>
    </div>
  );
}
